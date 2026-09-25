"""Carga de configuración: escenarios (sessions.yaml) y glosario (glossary.yaml)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

LANG_NAMES = {
    "es": "Español",
    "en": "English",
    "pt": "Português",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
}


@dataclass
class TalkConfig:
    """Una charla de la agenda de una sala. El hub la aplica sola cuando el reloj entra en su horario."""

    id: str
    name: str
    start: str  # "10:00" (hoy) o "2026-09-25T10:00", hora local
    end: str
    speaker: str = ""
    topic: str = ""
    language: str = ""  # vacío: el de la sala
    glossary: list[str] = field(default_factory=list)

    def window(self, now: datetime) -> tuple[datetime, datetime]:
        return _parse_when(self.start, now), _parse_when(self.end, now)


@dataclass
class SessionConfig:
    id: str
    name: str
    source: str = ""
    # "auto" deja que el modelo detecte el idioma de cada tramo (charlas en inglés con Q&A en español).
    language: str = "auto"
    speaker: str = ""
    topic: str = ""
    # Términos propios de esta charla que se suman al glosario global.
    glossary: list[str] = field(default_factory=list)
    # Si es False la fuente de archivo se lee a velocidad de reloj (-re) para simular un vivo.
    realtime: bool = True
    loop: bool = False
    # Agenda de la sala: nombre, orador, tema, idioma y glosario cambian solos según la hora.
    talks: list[TalkConfig] = field(default_factory=list)

    def current_and_next(self, now: datetime | None = None) -> tuple[TalkConfig | None, TalkConfig | None]:
        now = now or datetime.now()
        current, upcoming = None, None
        for talk in self.talks:
            start, end = talk.window(now)
            if start <= now < end:
                current = talk
            elif start > now and (upcoming is None or start < upcoming.window(now)[0]):
                upcoming = talk
        return current, upcoming


def _parse_when(value: str, now: datetime) -> datetime:
    value = str(value).strip()
    if len(value) <= 5 and ":" in value:  # "10:00"
        hour, minute = value.split(":")
        return now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    return datetime.fromisoformat(value)


@dataclass
class AppConfig:
    event: str = "Nerdearla 2026"
    languages: list[str] = field(default_factory=lambda: ["es", "en"])
    sessions: list[SessionConfig] = field(default_factory=list)
    glossary: list[str] = field(default_factory=list)
    engine: str = "gemini-live"
    data_dir: Path = Path("data")

    def session(self, sid: str) -> SessionConfig | None:
        return next((s for s in self.sessions if s.id == sid), None)


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_glossary(path: Path) -> list[str]:
    raw = _read_yaml(path)
    terms = raw.get("terms", raw if isinstance(raw, list) else [])
    return [str(t) for t in terms]


def load_config(sessions_path: str | Path = "config/sessions.yaml",
                glossary_path: str | Path = "config/glossary.yaml") -> AppConfig:
    raw = _read_yaml(Path(sessions_path))
    sessions = []
    for item in raw.get("sessions", []):
        item = dict(item)
        item["id"] = str(item["id"])
        item.setdefault("name", item["id"])
        talks = []
        for i, talk in enumerate(item.pop("talks", []) or []):
            talk = dict(talk)
            talk["id"] = str(talk.get("id") or f"{item['id']}-{i + 1}")
            talk["start"], talk["end"] = str(talk["start"]), str(talk["end"])
            talks.append(TalkConfig(**talk))
        sessions.append(SessionConfig(**item, talks=talks))
    languages = [str(lang) for lang in raw.get("languages", ["es", "en"])]
    return AppConfig(
        event=raw.get("event", "Nerdearla 2026"),
        languages=languages,
        sessions=sessions,
        glossary=load_glossary(Path(glossary_path)),
        engine=os.environ.get("SUBTITULA_ENGINE", raw.get("engine", "gemini-live")),
        data_dir=Path(os.environ.get("SUBTITULA_DATA", raw.get("data_dir", "data"))),
    )
