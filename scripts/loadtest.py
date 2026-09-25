"""Prueba de carga: N salas simultáneas y M personas leyendo por sala, sin gastar API.

  python scripts/loadtest.py --stages 20 --viewers 25 --seconds 60 [--mode live|chunks]

Mide el retraso de entrega del hub (publicación → pantalla) y cuánta CPU y memoria usa.

  --mode live    (por defecto) imita al motor en vivo: tres pistas por sala (original y dos
                 traducciones) cuyas líneas crecen de a un grupo de palabras cada 0,35 s. Es el
                 tráfico más exigente: cada actualización se reparte a cada pantalla.
  --mode chunks  imita al motor por tramos: workers reales con el motor falso, un subtítulo
                 completo cada ~3 s por sala.

Los clientes SSE corren en el mismo proceso que el hub, así que la CPU informada es la de los dos.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import socket
import statistics
import sys
import time
from pathlib import Path

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subtitula.captions import Caption  # noqa: E402
from subtitula.config import AppConfig, SessionConfig  # noqa: E402
from subtitula.hub import create_app  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "thor-schaeff-multilingual-agents-en.mp3"
WORDS = ("so the idea is that every stage gets its own live session and the audience "
         "reads the captions on their phone while the talk is happening").split()


async def viewer(base: str, sid: str, published: dict, delays: list[float], stop: asyncio.Event) -> None:
    async with httpx.AsyncClient(timeout=None) as http:
        async with http.stream("GET", f"{base}/api/sessions/{sid}/stream?since=999999") as resp:
            async for line in resp.aiter_lines():
                if stop.is_set():
                    return
                if line.startswith("data: "):
                    cap = json.loads(line[6:])
                    sent = published.get((sid, cap["seq"], len(cap["text"])), cap["created_at"])
                    delays.append((time.time() - sent) * 1000)


async def live_room(hub, sid: str, published: dict, counter: list[int], stop: asyncio.Event) -> None:
    """Tres pistas que crecen palabra por palabra, como las del motor en vivo."""

    async def track(name: str, original: bool, offset: float):
        await asyncio.sleep(offset)
        while not stop.is_set():
            cap = Caption(session=sid, seq=0, start=0, end=0, lang=name, text="", created_at=time.time(),
                          track=name, original=original)
            for i in range(0, 16, 2):  # ~8 actualizaciones por línea
                cap.text = " ".join(WORDS[i:i + 2]) if not cap.text else f"{cap.text} {' '.join(WORDS[i:i + 2])}"
                sent = time.time()
                cap.seq = await hub.caption(cap)
                published[(sid, cap.seq, len(cap.text))] = sent
                counter[0] += 1
                await asyncio.sleep(0.35)

    await asyncio.gather(track("en", True, 0), track("es", False, 0.4), track("pt", False, 0.7))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", type=int, default=10)
    ap.add_argument("--viewers", type=int, default=20)
    ap.add_argument("--seconds", type=int, default=45)
    ap.add_argument("--mode", choices=["live", "chunks"], default="live")
    args = ap.parse_args()
    os.environ.setdefault("SUBTITULA_FAKE_DELAY", "1.0")

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    source = str(SAMPLE) if args.mode == "chunks" else ""
    cfg = AppConfig(engine="fake", languages=["es", "en", "pt"], data_dir=Path("/tmp/subtitula-loadtest"),
                    sessions=[SessionConfig(id=f"sala-{i:02d}", name=f"Sala {i}", source=source, loop=True)
                              for i in range(args.stages)])
    app = create_app(cfg, run_workers=args.mode == "chunks")
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="warning"))
    serve = asyncio.create_task(server.serve())
    base = f"http://127.0.0.1:{port}"
    while not server.started:
        await asyncio.sleep(0.1)

    stop = asyncio.Event()
    delays: list[float] = []
    published: dict = {}
    counter = [0]
    viewers = [asyncio.create_task(viewer(base, s.id, published, delays, stop))
               for s in cfg.sessions for _ in range(args.viewers)]
    await asyncio.sleep(1)  # que se conecten todos antes de publicar
    rooms = [asyncio.create_task(live_room(app.state.hub, s.id, published, counter, stop))
             for s in cfg.sessions] if args.mode == "live" else []
    cpu0 = time.process_time()
    await asyncio.sleep(args.seconds)
    cpu = time.process_time() - cpu0
    async with httpx.AsyncClient() as http:
        status = (await http.get(f"{base}/api/status")).json()
    stop.set()
    for t in [*viewers, *rooms]:
        t.cancel()
    server.should_exit = True
    await asyncio.gather(serve, *viewers, *rooms, return_exceptions=True)

    rows = status["sessions"]
    delays.sort()
    published_n = counter[0] if args.mode == "live" else sum(r.get("captions", 0) for r in rows)
    print(f"Modo {args.mode}: {args.stages} salas, {status['viewers']} personas conectadas, {args.seconds} s")
    print(f"Actualizaciones publicadas: {published_n} ({published_n / args.seconds:.0f}/s)   "
          f"entregas SSE: {len(delays)} ({len(delays) / args.seconds:.0f}/s)")
    print(f"Errores: {sum(r.get('errors', 0) for r in rows)}   tramos salteados: {sum(r.get('dropped', 0) for r in rows)}")
    if delays:
        print(f"Entrega hub → pantalla: p50 {statistics.median(delays):.0f} ms, "
              f"p99 {delays[int(len(delays) * .99)]:.0f} ms")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"CPU (hub + clientes): {100 * cpu / args.seconds:.0f}% de un núcleo   memoria máx.: {rss:.0f} MB")


if __name__ == "__main__":
    asyncio.run(main())
