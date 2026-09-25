"""Sonda de la Live API: manda audio en tiempo real y muestra cada evento con su demora.

  python scripts/probe_live.py [modelo] [segundos]
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from subtitula.cli import load_dotenv  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "thor-schaeff-multilingual-agents-en.mp3"


async def main() -> None:
    load_dotenv()
    model = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.5-transcribe-live"
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 15
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-t", str(seconds), "-i", str(SAMPLE), "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    manual = os.environ.get("VAD") == "manual"
    vad = types.RealtimeInputConfig(automatic_activity_detection=types.AutomaticActivityDetection(
        disabled=True) if manual else types.AutomaticActivityDetection(
        silence_duration_ms=300, end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
        prefix_padding_ms=100))
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.TEXT] if "transcribe" in model else [types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig() if "transcribe" not in model else None,
        realtime_input_config=vad,
        translation_config=types.TranslationConfig(target_language_code=os.environ.get("TARGET", "es")) if "translate" in model else None,
    )
    t0 = time.time()
    async with client.aio.live.connect(model=model, config=config) as session:
        print(f"conectado en {time.time() - t0:.2f}s", flush=True)
        start = time.time()

        async def send():
            from subtitula.segmenter import Segmenter
            seg = Segmenter()
            chunk = 3200  # 100 ms
            if manual:
                await session.send_realtime_input(activity_start=types.ActivityStart())
            for i in range(0, len(pcm), chunk):
                await session.send_realtime_input(audio=types.Blob(data=pcm[i:i + chunk], mime_type="audio/pcm;rate=16000"))
                # Con VAD manual, cada corte del segmentador cierra un turno y abre otro.
                if manual:
                    for s in seg.feed(pcm[i:i + chunk]):
                        print(f"{time.time() - start:6.2f}s  corte {s.start:.1f}-{s.end:.1f}", flush=True)
                        await session.send_realtime_input(activity_end=types.ActivityEnd())
                        await session.send_realtime_input(activity_start=types.ActivityStart())
                await asyncio.sleep(0.1)
            if manual:
                await session.send_realtime_input(activity_end=types.ActivityEnd())
            else:
                await session.send_realtime_input(audio_stream_end=True)

        async def receive():
            async for msg in session.receive():
                t = time.time() - start
                sc = msg.server_content
                if sc and sc.input_transcription and sc.input_transcription.text:
                    print(f"{t:6.2f}s  IN   {sc.input_transcription.text!r}", flush=True)
                if sc and sc.output_transcription and sc.output_transcription.text:
                    print(f"{t:6.2f}s  OUT  {sc.output_transcription.text!r}", flush=True)
                if sc and sc.model_turn:
                    for part in sc.model_turn.parts or []:
                        if part.text:
                            print(f"{t:6.2f}s  TEXT {part.text!r}", flush=True)
                        if part.inline_data and os.environ.get("SHOW_AUDIO"):
                            print(f"{t:6.2f}s  AUDIO {len(part.inline_data.data)} bytes {part.inline_data.mime_type}", flush=True)
                        if part.inline_data and os.environ.get("SAVE_AUDIO"):
                            with open(os.environ["SAVE_AUDIO"], "ab") as fh:
                                fh.write(part.inline_data.data)
                if os.environ.get("SHOW_ALL") and not (sc and sc.input_transcription):
                    print(f"{t:6.2f}s  MSG {str(msg.model_dump(exclude_none=True))[:200]}", flush=True)
                if msg.go_away or (sc and sc.turn_complete and t > seconds):
                    print(f"{t:6.2f}s  fin ({'go_away' if msg.go_away else 'turn_complete'})")
                    return

        sender = asyncio.create_task(send())
        try:
            await asyncio.wait_for(receive(), timeout=seconds + 20)
        except asyncio.TimeoutError:
            print("fin por tiempo")
        sender.cancel()


if __name__ == "__main__":
    asyncio.run(main())
