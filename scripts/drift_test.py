"""¿La traducción se atrasa en una charla larga? Demora minuto a minuto con el motor en vivo.

  python scripts/drift_test.py charla.mp3 --language en --targets es [--out informe.json]

Pasa el archivo a velocidad real por el motor `gemini-live` (como si fuera el vivo) y, por
cada minuto, informa la demora del original y de la traducción: el tiempo entre que el orador
hace una pausa y que llega la última palabra de esa frase. Si la traducción se fuera atrasando,
esa demora crecería minuto a minuto.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subtitula.captions import Caption  # noqa: E402
from subtitula.cli import load_dotenv  # noqa: E402
from subtitula.config import SessionConfig  # noqa: E402


class Timed(list):
    """Lista que recuerda cuándo se agregó cada valor."""

    def __init__(self):
        super().__init__()
        self.times: list[float] = []

    def append(self, value) -> None:
        super().append(value)
        self.times.append(time.time())


class Collector:
    def __init__(self):
        self.by_seq: dict[int, Caption] = {}

    async def caption(self, cap: Caption) -> int:
        self.by_seq[cap.seq] = Caption.from_dict(cap.to_dict())
        return cap.seq

    async def status(self, session: str, status: dict) -> None:
        return None


def pct(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


def window(timed: Timed, start: float, end: float) -> list[int]:
    return [v for v, t in zip(timed, timed.times) if start <= t < end]


async def main() -> None:
    load_dotenv()
    from subtitula.live import LiveEngine, LiveSessionWorker

    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--language", default="en")
    ap.add_argument("--targets", default="es")
    ap.add_argument("--out")
    args = ap.parse_args()

    session = SessionConfig(id=Path(args.path).stem, name=Path(args.path).stem, source=args.path,
                            language=args.language, realtime=True)
    out = Collector()
    worker = LiveSessionWorker(session, LiveEngine(), out, args.targets.split(","), [])
    worker.latencies, worker.tr_latencies = Timed(), Timed()
    started = time.time()
    await worker.run()
    minutes = int((time.time() - started) // 60) + 1

    rows = []
    for m in range(minutes):
        a, b = started + 60 * m, started + 60 * (m + 1)
        orig, trad = window(worker.latencies, a, b), window(worker.tr_latencies, a, b)
        rows.append({"minuto": m + 1, "original_p50_ms": pct(orig, 0.5), "original_p90_ms": pct(orig, 0.9),
                     "traduccion_p50_ms": pct(trad, 0.5), "traduccion_p90_ms": pct(trad, 0.9),
                     "frases_medidas": len(orig) + len(trad)})
    caps = list(out.by_seq.values())
    tracks = {c.track: sum(1 for x in caps if x.track == c.track) for c in caps}
    print(f"{'min':>3}  {'orig p50':>9} {'orig p90':>9}  {'trad p50':>9} {'trad p90':>9}  frases")
    for r in rows:
        f = lambda v: f"{v / 1000:.2f} s" if v is not None else "   -   "  # noqa: E731
        print(f"{r['minuto']:>3}  {f(r['original_p50_ms']):>9} {f(r['original_p90_ms']):>9}  "
              f"{f(r['traduccion_p50_ms']):>9} {f(r['traduccion_p90_ms']):>9}  {r['frases_medidas']:>6}")
    all_o, all_t = list(worker.latencies), list(worker.tr_latencies)
    summary = {"archivo": args.path, "minutos": minutes, "lineas_por_pista": tracks,
               "original_p50_ms": pct(all_o, 0.5), "original_p90_ms": pct(all_o, 0.9),
               "traduccion_p50_ms": pct(all_t, 0.5), "traduccion_p90_ms": pct(all_t, 0.9),
               "errores": worker.errors, "reconexiones": sum(t.reconnects for t in worker.tracks),
               "costo_usd": round(worker.cost_usd, 3), "por_minuto": rows}
    print(f"Total: original p50 {summary['original_p50_ms']} ms / p90 {summary['original_p90_ms']} ms, "
          f"traducción p50 {summary['traduccion_p50_ms']} ms / p90 {summary['traduccion_p90_ms']} ms, "
          f"líneas {tracks}, errores {worker.errors}, costo US$ {summary['costo_usd']}")
    if args.out:
        Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
