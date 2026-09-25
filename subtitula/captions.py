"""Modelo de subtítulo y exportación a SRT, WebVTT y texto plano."""

from __future__ import annotations

import textwrap
from dataclasses import asdict, dataclass, field


@dataclass
class Caption:
    session: str
    seq: int
    start: float  # segundos de audio desde el inicio de la sesión
    end: float
    lang: str  # idioma detectado del tramo
    text: str  # transcripción en el idioma original
    tr: dict[str, str] = field(default_factory=dict)  # traducciones por código de idioma
    latency_ms: int = 0  # desde que terminó el audio del tramo hasta que se publicó
    created_at: float = 0.0
    pending: bool = False  # la traducción todavía no llegó (motor en dos etapas)
    tr_latency_ms: int = 0  # desde que terminó el audio hasta que llegó la traducción
    # Motor en vivo: cada idioma es una pista con sus propias líneas. `track` es el idioma de la
    # pista y `original` marca la del idioma hablado. Vacío: una línea con todas las traducciones.
    track: str = ""
    original: bool = False

    def visible_in(self, lang: str) -> bool:
        if not self.track:
            return True
        if lang in ("", "original"):
            return self.original
        return self.track == lang

    def in_lang(self, lang: str) -> str:
        if self.track or lang in ("", "original", self.lang):
            return self.text
        return self.tr.get(lang) or self.text

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Caption":
        fields = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**fields)


def _ts(seconds: float, sep: str) -> str:
    ms = int(round(max(seconds, 0.0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _wrap(text: str, width: int = 42) -> str:
    # 42 caracteres por línea es la norma de subtitulado más difundida.
    return "\n".join(textwrap.wrap(text, width=width)) or text


def _visible(captions: list[Caption], lang: str) -> list[Caption]:
    return [c for c in captions if c.visible_in(lang)]


def to_srt(captions: list[Caption], lang: str = "original") -> str:
    captions = _visible(captions, lang)
    blocks = []
    for i, cap in enumerate(c for c in captions if c.in_lang(lang).strip()):
        blocks.append(f"{i + 1}\n{_ts(cap.start, ',')} --> {_ts(cap.end, ',')}\n{_wrap(cap.in_lang(lang))}\n")
    return "\n".join(blocks)


def to_vtt(captions: list[Caption], lang: str = "original") -> str:
    blocks = ["WEBVTT\n"]
    for cap in _visible(captions, lang):
        text = cap.in_lang(lang).strip()
        if text:
            blocks.append(f"{_ts(cap.start, '.')} --> {_ts(cap.end, '.')}\n{_wrap(text)}\n")
    return "\n".join(blocks)


def to_txt(captions: list[Caption], lang: str = "original") -> str:
    paragraphs, current, last_end = [], [], None
    for cap in _visible(captions, lang):
        text = cap.in_lang(lang).strip()
        if not text:
            continue
        # Una pausa larga del orador abre un párrafo nuevo.
        if last_end is not None and cap.start - last_end > 2.5 and current:
            paragraphs.append(" ".join(current))
            current = []
        current.append(text)
        last_end = cap.end
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs) + "\n"
