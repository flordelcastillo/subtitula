"""Chequeo de credenciales y latencia por modelo, antes del evento.

  python scripts/check_gemini.py

Pasa dos tramos reales de la charla de ejemplo por las dos etapas del motor (transcripción y
traducción) y muestra, por modelo, si responde, cuánto tarda y qué devuelve. Hace unos 5
pedidos en total: con la clave gratuita conviene no correrlo varias veces seguidas.
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


def clip(start: float, seconds: float) -> Segment:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(seconds), "-i", str(SAMPLE),
                          "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return Segment(pcm=pcm, start=start, end=start + seconds, speech_ratio=1.0)


async def main() -> None:
    load_dotenv()
    from subtitula.engines.gemini import GeminiEngine

    engine = GeminiEngine()
    ctx = EngineContext(session_name="Building Multilingual Conversational AI Agents", languages=["es", "en", "pt"],
                        source_language="en", glossary=["ElevenLabs", "Gemini", "Nerdearla"], speaker="Thor Schaeff")
    print(f"Transcripción con {', '.join(engine.asr.models)}")
    texts = []
    for seg in (clip(21.7, 3.8), clip(46.4, 4.0)):
        start = time.time()
        try:
            res = await engine.process(seg, ctx)
            texts.append(res.text)
            print(f"  {time.time() - start:5.2f}s  {res.text!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {time.time() - start:5.2f}s  FALLA {type(exc).__name__}: {str(exc)[:110]}")
    if not texts:
        return
    print("Traducción, un pedido por modelo del pool:")
    for model in list(engine.translators.models):
        single = GeminiEngine(model=model)
        start = time.time()
        try:
            res = await single.translate(texts[0], "en", ctx)
            print(f"  {model:26} {time.time() - start:5.2f}s  es={res.tr.get('es', '')!r}  pt={res.tr.get('pt', '')!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {model:26} {time.time() - start:5.2f}s  FALLA {type(exc).__name__}: {str(exc)[:90]}")


if __name__ == "__main__":
    asyncio.run(main())
