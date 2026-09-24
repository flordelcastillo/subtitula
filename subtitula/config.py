"""Carga de configuración: escenarios (sessions.yaml) y glosario (glossary.yaml)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
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


@dataclass
class AppConfig:
    event: str = "Nerdearla 2026"
    languages: list[str] = field(default_factory=lambda: ["es", "en"])
    sessions: list[SessionConfig] = field(default_factory=list)
    glossary: list[str] = field(default_factory=list)
    engine: str = "gemini"
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
        sessions.append(SessionConfig(**item))
    languages = [str(lang) for lang in raw.get("languages", ["es", "en"])]
    return AppConfig(
        event=raw.get("event", "Nerdearla 2026"),
        languages=languages,
        sessions=sessions,
        glossary=load_glossary(Path(glossary_path)),
        engine=os.environ.get("SUBTITULA_ENGINE", raw.get("engine", "gemini")),
        data_dir=Path(os.environ.get("SUBTITULA_DATA", raw.get("data_dir", "data"))),
    )
