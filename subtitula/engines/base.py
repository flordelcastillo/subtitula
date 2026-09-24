"""Interfaz común de los motores de transcripción y traducción."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass, field

from ..segmenter import SAMPLE_RATE, Segment


@dataclass
class EngineContext:
    session_name: str
    languages: list[str]  # idiomas de salida del evento
    source_language: str = "auto"
    glossary: list[str] = field(default_factory=list)
    speaker: str = ""
    topic: str = ""
    # Últimos tramos transcriptos: dan continuidad a frases cortadas y a nombres ya escuchados.
    previous: list[str] = field(default_factory=list)


@dataclass
class EngineResult:
    lang: str
    text: str
    tr: dict[str, str] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class Engine:
    name = "base"
    # Si es True, process() devuelve sólo la transcripción y translate() agrega las traducciones.
    two_stage = False

    async def process(self, segment: Segment, ctx: EngineContext) -> EngineResult:
        raise NotImplementedError

    async def translate(self, text: str, lang: str, ctx: EngineContext) -> EngineResult:
        raise NotImplementedError

    async def close(self) -> None:
        return None


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()


def create_engine(name: str) -> Engine:
    name = (name or "gemini").lower()
    if name == "gemini":
        from .gemini import GeminiEngine
        return GeminiEngine()
    if name == "local":
        from .local import LocalEngine
        return LocalEngine()
    if name == "fake":
        from .fake import FakeEngine
        return FakeEngine()
    raise ValueError(f"Motor desconocido: {name} (opciones: gemini, local, fake)")
