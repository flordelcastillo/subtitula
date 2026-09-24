"""Prueba de carga: N escenarios simultáneos y M personas leyendo por escenario, sin gastar API.

  python scripts/loadtest.py --stages 20 --viewers 25 --seconds 60

Levanta un hub, lanza N workers con el motor falso (misma forma de tráfico que Gemini:
un pedido por tramo de ~3 s) y abre M conexiones SSE por escenario. Mide el retraso de
entrega del hub (publicación → pantalla) y cuánta CPU y memoria usa.
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
from subtitula.config import AppConfig, SessionConfig  # noqa: E402
from subtitula.hub import create_app  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "thor-schaeff-multilingual-agents-en.mp3"


async def viewer(base: str, sid: str, delays: list[float], stop: asyncio.Event) -> None:
    async with httpx.AsyncClient(timeout=None) as http:
        async with http.stream("GET", f"{base}/api/sessions/{sid}/stream?since=999999") as resp:
            async for line in resp.aiter_lines():
                if stop.is_set():
                    return
                if line.startswith("data: "):
                    cap = json.loads(line[6:])
                    delays.append((time.time() - cap["created_at"]) * 1000)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", type=int, default=10)
    ap.add_argument("--viewers", type=int, default=20)
    ap.add_argument("--seconds", type=int, default=45)
    args = ap.parse_args()
    os.environ.setdefault("SUBTITULA_FAKE_DELAY", "1.0")

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    cfg = AppConfig(engine="fake", languages=["es", "en", "pt"], data_dir=Path("/tmp/subtitula-loadtest"),
                    sessions=[SessionConfig(id=f"sala-{i:02d}", name=f"Sala {i}", source=str(SAMPLE), loop=True)
                              for i in range(args.stages)])
    server = uvicorn.Server(uvicorn.Config(create_app(cfg, run_workers=True), port=port, log_level="warning"))
    serve = asyncio.create_task(server.serve())
    base = f"http://127.0.0.1:{port}"
    while not server.started:
        await asyncio.sleep(0.1)

    stop = asyncio.Event()
    delays: list[float] = []
    viewers = [asyncio.create_task(viewer(base, s.id, delays, stop))
               for s in cfg.sessions for _ in range(args.viewers)]
    cpu0 = time.process_time()
    await asyncio.sleep(args.seconds)
    cpu = time.process_time() - cpu0
    async with httpx.AsyncClient() as http:
        status = (await http.get(f"{base}/api/status")).json()
    stop.set()
    for t in viewers:
        t.cancel()
    server.should_exit = True
    await asyncio.gather(serve, *viewers, return_exceptions=True)

    rows = status["sessions"]
    lat = [r["latency_p50_ms"] for r in rows if r.get("latency_p50_ms")]
    delays.sort()
    print(f"Escenarios: {args.stages}   personas conectadas: {status['viewers']}")
    print(f"Subtítulos publicados: {sum(r.get('captions', 0) for r in rows)}   entregas SSE: {len(delays)}")
    print(f"Tramos salteados: {sum(r.get('dropped', 0) for r in rows)}   errores: {sum(r.get('errors', 0) for r in rows)}")
    if delays:
        print(f"Entrega hub → pantalla: p50 {statistics.median(delays):.0f} ms, p99 {delays[int(len(delays) * .99)]:.0f} ms")
    if lat:
        print(f"Latencia de motor simulado (p50 por sala): {statistics.median(lat):.0f} ms")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"CPU del proceso: {100 * cpu / args.seconds:.0f}% de un núcleo   memoria máx.: {rss:.0f} MB")


if __name__ == "__main__":
    asyncio.run(main())
