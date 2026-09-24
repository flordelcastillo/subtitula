"""Chequeo de credenciales y latencia por modelo, antes del evento.

  python scripts/check_gemini.py [modelo ...]

Manda tramos reales de la charla de ejemplo por el mismo camino que usa el worker (prompt,
glosario y salida JSON) y muestra, por modelo, si responde, cuánto tarda y qué devuelve.
Hace dos pedidos por modelo: cuidado con la cuota gratuita (15 pedidos/min por modelo).
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subtitula.cli import load_dotenv  # noqa: E402
from subtitula.engines.base import EngineContext  # noqa: E402
from subtitula.segmenter import Segment  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "thor-schaeff-multilingual-agents-en.mp3"
CANDIDATES = ["gemini-3.5-transcribe", "gemini-omni-1.1-flash", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-3-flash-preview", "gemini-flash-latest"]


def clip(start: float, seconds: float) -> Segment:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(seconds), "-i", str(SAMPLE),
                          "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return Segment(pcm=pcm, start=start, end=start + seconds, speech_ratio=1.0)


async def main() -> None:
    load_dotenv()
    from subtitula.engines.gemini import GeminiEngine

    models = sys.argv[1:] or CANDIDATES
    ctx = EngineContext(session_name="Building Multilingual Conversational AI Agents", languages=["es", "en", "pt"],
                        source_language="en", glossary=["ElevenLabs", "Gemini", "Nerdearla"], speaker="Thor Schaeff")
    segments = [clip(21.7, 3.8), clip(46.4, 4.0)]
    for model in models:
        engine = GeminiEngine(model=model)
        for seg in segments:
            start = time.time()
            try:
                res = await engine.process(seg, ctx)
                print(f"{model:24} {time.time() - start:5.2f}s  {res.lang}  {res.text[:70]!r}  es={res.tr.get('es', '')[:60]!r}")
            except Exception as exc:  # noqa: BLE001
                print(f"{model:24} {time.time() - start:5.2f}s  FALLA {type(exc).__name__}: {str(exc)[:110]}")


if __name__ == "__main__":
    asyncio.run(main())
