"""Fuentes de audio. Todo se normaliza a PCM s16le mono 16 kHz con ffmpeg.

Formatos de `source` aceptados:
  samples/charla.mp3           archivo local (se lee a velocidad real para simular un vivo)
  mic  |  mic:<dispositivo>     micrófono (PulseAudio/PipeWire en Linux, avfoundation en macOS)
  https://.../stream.m3u8       HLS, Icecast, cualquier URL que ffmpeg abra
  rtmp://  srt://  udp://       ingest de un encoder (OBS, vMix, consola de sonido)
  https://youtube.com/...       YouTube en vivo o grabado (requiere yt-dlp)
  browser                       audio enviado desde la página /enviar por WebSocket
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from collections.abc import AsyncIterator
from pathlib import Path

from .segmenter import SAMPLE_RATE

log = logging.getLogger(__name__)

CHUNK_BYTES = SAMPLE_RATE * 2 // 10  # 100 ms


def is_live(source: str) -> bool:
    return not Path(source).exists()


def is_youtube(source: str) -> bool:
    return any(h in source for h in ("youtube.com/", "youtu.be/"))


async def resolve_youtube(url: str) -> tuple[str, bool]:
    """Devuelve la URL directa del audio y si la transmisión es en vivo."""
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        raise RuntimeError("Para fuentes de YouTube instalá yt-dlp (pip install yt-dlp)")
    proc = await asyncio.create_subprocess_exec(
        ytdlp, "-f", "bestaudio/best", "-g", "--print", "is_live", url,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp falló: {err.decode(errors='ignore').strip()[-300:]}")
    lines = [ln for ln in out.decode().splitlines() if ln.strip()]
    live = lines[0].strip().lower() == "true"
    return lines[-1].strip(), live


def ffmpeg_input_args(source: str, realtime: bool = True, loop: bool = False) -> list[str]:
    if source == "mic" or source.startswith("mic:"):
        device = source.partition(":")[2] or ("default" if sys.platform != "darwin" else ":0")
        fmt = "avfoundation" if sys.platform == "darwin" else "pulse"
        return ["-f", fmt, "-i", device]
    path = Path(source)
    if path.exists():
        args = []
        if realtime:
            args.append("-re")
        if loop:
            args += ["-stream_loop", "-1"]
        return args + ["-i", str(path)]
    args = []
    if source.startswith(("http://", "https://")):
        args += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
    return args + ["-i", source]


def ffmpeg_command(source: str, realtime: bool = True, loop: bool = False) -> list[str]:
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            *ffmpeg_input_args(source, realtime, loop),
            "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1"]


async def ffmpeg_pcm(source: str, realtime: bool = True, loop: bool = False) -> AsyncIterator[bytes]:
    if is_youtube(source):
        source, live = await resolve_youtube(source)
        # Un video grabado se lee a velocidad real para que se comporte como un vivo.
        realtime = realtime and not live
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
               *(["-re"] if realtime else []), "-i", source,
               "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1"]
    else:
        cmd = ffmpeg_command(source, realtime, loop)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        assert proc.stdout is not None
        while True:
            chunk = await proc.stdout.read(CHUNK_BYTES)
            if not chunk:
                break
            yield chunk
        await proc.wait()
        if proc.returncode not in (0, None):
            err = (await proc.stderr.read()).decode(errors="ignore").strip() if proc.stderr else ""
            raise RuntimeError(f"ffmpeg terminó con código {proc.returncode}: {err[-300:]}")
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


class QueueSource:
    """Fuente alimentada desde afuera (WebSocket del navegador)."""

    def __init__(self):
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        self.connected = 0

    def put(self, pcm: bytes) -> None:
        try:
            self.queue.put_nowait(pcm)
        except asyncio.QueueFull:
            # Si el procesamiento se atrasa se descarta audio viejo: el vivo manda.
            self.queue.get_nowait()
            self.queue.put_nowait(pcm)

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while True:
            yield await self.queue.get()
