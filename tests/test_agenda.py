"""Agenda por sala: la charla vigente se aplica sola por reloj (nombre, orador, glosario, idioma)."""

from datetime import datetime

from subtitula.config import AppConfig, SessionConfig, TalkConfig, load_config
from subtitula.hub import Hub


def room():
    return SessionConfig(
        id="auditorio", name="Auditorio", speaker="", language="es", glossary=["Nerdearla"],
        talks=[
            TalkConfig(id="apertura", name="Apertura", start="09:30", end="10:00", speaker="Ariel Jolo"),
            TalkConfig(id="thor", name="What's new in AI Audio?", start="12:10", end="12:50", speaker="Thor Schaeff",
                       language="en", glossary=["ElevenLabs = 11 labs", "Gemini Live API"]),
        ],
    )


def test_current_and_next_by_clock():
    s = room()
    at = lambda h, m: datetime(2026, 9, 25, h, m)  # noqa: E731
    assert [t.id if t else None for t in s.current_and_next(at(9, 0))] == [None, "apertura"]
    assert [t.id if t else None for t in s.current_and_next(at(9, 45))] == ["apertura", "thor"]
    assert [t.id if t else None for t in s.current_and_next(at(12, 30))] == ["thor", None]
    assert s.current_and_next(at(13, 0)) == (None, None)


def test_load_config_parses_talks(tmp_path):
    (tmp_path / "sessions.yaml").write_text(
        "sessions:\n  - id: a\n    name: Sala A\n    talks:\n      - {name: Charla, start: '10:00', end: '10:40', speaker: X}\n"
        "      - {id: dos, name: Otra, start: 2026-09-25T11:00, end: 2026-09-25T11:30, language: en}\n",
        encoding="utf-8")
    cfg = load_config(tmp_path / "sessions.yaml", tmp_path / "no.yaml")
    talks = cfg.sessions[0].talks
    assert [t.id for t in talks] == ["a-1", "dos"] and talks[1].language == "en"
    start, end = talks[1].window(datetime(2026, 9, 25, 9, 0))
    assert (start.hour, end.minute) == (11, 30)


def test_hub_applies_agenda_and_reverts(tmp_path):
    hub = Hub(AppConfig(data_dir=tmp_path, glossary=["Konex"], sessions=[room()]))

    class FakeWorker:
        glossary: list[str] = []
        language = ""

        def set_glossary(self, terms):
            self.glossary = list(terms)

        def set_language(self, language):
            self.language = language

    worker = FakeWorker()
    hub.workers["auditorio"] = worker

    assert hub.apply_agenda(datetime(2026, 9, 25, 12, 20)) == ["auditorio"]
    meta = hub.meta["auditorio"]
    assert (meta.name, meta.speaker, meta.language) == ("What's new in AI Audio?", "Thor Schaeff", "en")
    assert hub.glossary["auditorio"] == ["Konex", "Nerdearla", "ElevenLabs = 11 labs", "Gemini Live API"]
    assert worker.language == "en" and "Gemini Live API" in worker.glossary
    info = hub.session_info("auditorio")
    assert info["agenda"]["now"]["id"] == "thor" and info["agenda"]["next"] is None
    assert hub.apply_agenda(datetime(2026, 9, 25, 12, 25)) == []  # sin cambios, no se toca nada

    # Terminó la charla: la sala vuelve a su configuración base.
    assert hub.apply_agenda(datetime(2026, 9, 25, 13, 0)) == ["auditorio"]
    assert (meta.name, meta.language) == ("Auditorio", "es") and worker.language == "es"
    assert hub.glossary["auditorio"] == ["Konex", "Nerdearla"]
