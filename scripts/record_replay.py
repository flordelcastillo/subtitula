"""Graba una corrida real del motor en vivo para la demo de repetición y la evidencia de calidad.

  python scripts/record_replay.py samples/charla.mp3 --id sala-a --name "..." --language en \
      --targets es,pt --out demo/data

Pasa el archivo a velocidad real por `gemini-live` y guarda:
  <id>.json        cada actualización de subtítulo con su posición en el audio (segundos)
  <id>.<lang>.wav  la interpretación hablada, ubicada en el tiempo como la reproduce el celular
  <id>.<pista>.srt los subtítulos finales de cada pista
La página demo/index.html reproduce el audio y muestra los subtítulos tal como salieron.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subtitula.captions import Caption, to_srt  # noqa: E402
from subtitula.cli import load_dotenv  # noqa: E402
from subtitula.config import SessionConfig  # noqa: E402


class Recorder:
    def __init__(self):
        self.worker = None
        self.updates: list[tuple[float, dict]] = []
        self.final: dict[int, Caption] = {}
        self.voices: dict[str, dict] = {}

    async def caption(self, cap: Caption) -> int:
        pos = round(self.worker._audio_pos(), 2)
        self.updates.append((pos, {k: getattr(cap, k) for k in ("seq", "track", "original", "lang", "text")}))
        self.final[cap.seq] = Caption.from_dict(cap.to_dict())
        return cap.seq

    async def status(self, session: str, status: dict) -> None:
        return None

    def speech(self, sid: str, lang: str, pcm: bytes, rate: int) -> None:
        """Ubica cada bloque de voz como el reproductor del celular (saltea silencios si se atrasa)."""
        st = self.voices.setdefault(lang, {"rate": rate, "pcm": np.zeros(0, dtype=np.int16), "next": 0.0})
        now = self.worker._audio_pos()
        samples = np.frombuffer(pcm, dtype=np.int16)
        frame = int(rate * 0.05)
        if st["next"] < now + 0.05:
            st["next"] = now + 0.15
        for i in range(0, len(samples), frame):
            chunk = samples[i:i + frame]
            rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2))) / 32768 if len(chunk) else 0.0
            ahead = st["next"] - now
            if (ahead > 0.4 and rms < 0.01) or ahead > 3:
                continue
            pos = int(st["next"] * rate)
            if len(st["pcm"]) < pos + len(chunk):
                st["pcm"] = np.concatenate([st["pcm"], np.zeros(pos + len(chunk) - len(st["pcm"]), dtype=np.int16)])
            st["pcm"][pos:pos + len(chunk)] = chunk
            st["next"] += len(chunk) / rate


async def main() -> None:
    load_dotenv()
    from subtitula.live import LiveEngine, LiveSessionWorker

    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--speaker", default="")
    ap.add_argument("--language", default="en")
    ap.add_argument("--targets", default="es,pt")
    ap.add_argument("--glossary", default="")
    ap.add_argument("--out", default="demo/data")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    session = SessionConfig(id=args.id, name=args.name, speaker=args.speaker, source=args.path,
                            language=args.language, realtime=True)
    rec = Recorder()
    glossary = [t.strip() for t in args.glossary.split(",") if t.strip()]
    worker = LiveSessionWorker(session, LiveEngine(), rec, args.targets.split(","), glossary)
    rec.worker = worker
    started = time.time()
    await worker.run()
    st = worker.status()

    tracks = sorted({c.track for c in rec.final.values()})
    speech_files = {}
    for lang, data in rec.voices.items():
        path = out / f"{args.id}.{lang}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(data["rate"])
            w.writeframes(data["pcm"].tobytes())
        speech_files[lang] = path.name
    caps = [rec.final[k] for k in sorted(rec.final)]
    for track in tracks:
        lang = "original" if any(c.original and c.track == track for c in caps) else track
        (out / f"{args.id}.{track}.srt").write_text(to_srt(caps, lang), encoding="utf-8")
    meta = {
        "id": args.id, "name": args.name, "speaker": args.speaker, "language": args.language,
        "targets": args.targets.split(","), "recorded_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(started)),
        "model": worker.engine.model, "speech": speech_files,
        "stats": {k: st.get(k) for k in ("latency_p50_ms", "latency_p90_ms", "translation_p50_ms",
                                         "translation_p90_ms", "errors", "lag_cuts", "cost_usd")},
        "updates": rec.updates,
    }
    (out / f"{args.id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print(f"{args.id}: {len(rec.updates)} actualizaciones, pistas {tracks}, voz {list(speech_files)}, "
          f"stats {meta['stats']}")


if __name__ == "__main__":
    asyncio.run(main())
