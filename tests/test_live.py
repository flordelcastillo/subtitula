"""Motor en vivo sin red: se alimentan fragmentos como los que manda la Live API."""

import time

from subtitula.captions import Caption, to_srt, to_txt
from subtitula.config import SessionConfig
from subtitula.engines.fake import FakeEngine
from subtitula.live import LiveSessionWorker


class Collector:
    def __init__(self):
        self.by_seq: dict[int, Caption] = {}

    async def caption(self, cap: Caption) -> int:
        self.by_seq[cap.seq] = Caption.from_dict(cap.to_dict())
        return cap.seq

    async def status(self, session: str, status: dict) -> None:
        return None

    def track(self, name: str) -> list[str]:
        return [c.text for _, c in sorted(self.by_seq.items()) if c.track == name]


def make_worker(language="en"):
    session = SessionConfig(id="sala", name="Sala", source="browser", language=language)
    out = Collector()
    worker = LiveSessionWorker(session, FakeEngine(delay_s=0), out, ["es", "en", "pt"], ["Nerdearla"])
    return worker, out


async def test_tracks_split_on_sentences_inside_a_fragment():
    worker, out = make_worker()
    # Con idioma conocido hay una sesión por cada idioma de destino y la pista original es "en".
    assert [t.target for t in worker.tracks] == ["es", "pt"]
    for delta in ["That's a good point.", " We didn't. Can I share", " the audio on this stream?"]:
        await worker.on_original(delta, "en")
    for delta in ["Buen punto. No lo hicimos.", " ¿Puedo compartir el audio?"]:
        await worker.on_translation("es", delta)
    # Una oración de menos de 15 caracteres no cierra la línea: se evita que parpadeen líneas mínimas.
    assert out.track("en") == ["That's a good point.", "We didn't. Can I share the audio on this stream?"]
    assert out.track("es") == ["Buen punto. No lo hicimos.", "¿Puedo compartir el audio?"]
    assert all(c.original for c in out.by_seq.values() if c.track == "en")


async def test_long_lines_are_capped_for_subtitles():
    worker, out = make_worker()
    words = " ".join(["kubernetes"] * 30)
    for word in words.split(" "):
        await worker.on_original(" " + word, "en")
    assert all(len(line) <= 84 for line in out.track("en"))
    assert " ".join(out.track("en")) == words


async def test_exports_pick_the_right_track():
    worker, out = make_worker()
    await worker.on_original("Hello everyone.", "en")
    await worker.on_translation("es", "Hola a todos.")
    await worker.on_translation("pt", "Olá a todos.")
    caps = [c for _, c in sorted(out.by_seq.items())]
    assert to_txt(caps, "es") == "Hola a todos.\n"
    assert to_txt(caps, "original") == "Hello everyone.\n"
    assert to_txt(caps, "en") == "Hello everyone.\n"
    assert "Olá a todos." in to_srt(caps, "pt") and "Hola" not in to_srt(caps, "pt")


async def test_auto_language_uses_a_separate_original_track():
    worker, out = make_worker(language="auto")
    assert [t.target for t in worker.tracks] == ["es", "en", "pt"]
    await worker.on_original("Hola, ¿se escucha?", "es")
    cap = next(iter(out.by_seq.values()))
    assert cap.track == "original" and cap.lang == "es" and cap.visible_in("original")
    assert not cap.visible_in("es")


async def test_languages_on_demand():
    worker, _ = make_worker()
    es, pt = worker.tracks
    assert es.primary and not pt.primary
    worker.set_demand([])  # al arrancar hay un período de gracia: todo abierto
    assert pt.wanted.is_set()
    worker.started_at -= 1000  # pasó la gracia
    worker.set_demand([])
    assert es.wanted.is_set() and not pt.wanted.is_set()
    pt.put(b"\x00\x00" * 1600)  # sin público, el audio ni se encola
    assert pt.queue.empty()
    worker.set_demand(["pt"])
    assert pt.wanted.is_set()
    worker.demand_until["pt"] = time.time() - 1  # pasó el tiempo de espera sin público
    worker.set_demand(["es"])
    assert not pt.wanted.is_set() and es.wanted.is_set()


async def test_long_silence_is_not_sent():
    import numpy as np

    worker, _ = make_worker()
    worker.pause_after_s = 1.0
    silence = np.zeros(1600, dtype=np.int16).tobytes()
    voice = (np.sin(np.arange(1600) / 5) * 8000).astype(np.int16).tobytes()
    es = worker.tracks[0]
    for _ in range(30):  # 3 s de silencio
        worker._on_audio(silence)
        worker._forward(silence)
    sent_before_pause = es.queue.qsize()
    assert worker.paused and sent_before_pause <= 11
    assert worker.saved_audio_s > 1.5
    worker._on_audio(voice)
    worker._forward(voice)
    # Al volver la voz se manda también el medio segundo previo, para no perder la primera sílaba.
    assert not worker.paused and es.queue.qsize() == sent_before_pause + 5 + 1


def test_hub_demand_from_viewers_and_listeners(tmp_path):
    import asyncio

    from subtitula.config import AppConfig
    from subtitula.hub import Hub

    hub = Hub(AppConfig(data_dir=tmp_path, sessions=[SessionConfig(id="sala", name="Sala")]))
    hub.watch("sala", "es")
    hub.watch("otra", "pt")  # sala inexistente: se ignora
    hub.listeners[("sala", "pt")] = {asyncio.Queue()}
    assert hub.demand_for("sala") == ["es", "pt"]
    hub.demand[("sala", "es")] -= 60
    assert hub.demand_for("sala") == ["pt"]


def test_glossary_fixer_canonical_spelling():
    from subtitula.glossary import GlossaryFixer

    g = GlossaryFixer(["ElevenLabs", "Nerdearla", "kubectl", "GitHub", "Thor Schaeff", "RAG", "open source"])
    assert g.fix("we use eleven labs on github") == "we use ElevenLabs on GitHub"
    assert g.fix("Bienvenidos a nerdearla, usá Kubectl") == "Bienvenidos a Nerdearla, usá kubectl"
    assert g.fix("thor schaeff habla de rag") == "Thor Schaeff habla de RAG"
    assert g.fix("Open Source es genial") == "Open source es genial"  # conserva la mayúscula inicial
    assert g.fix("drag and drop, el llamado") == "drag and drop, el llamado"  # sin falsos positivos


async def test_live_tracks_apply_glossary_and_hot_reload():
    worker, out = make_worker()
    await worker.on_translation("es", "Bienvenidos a nerdearla")
    assert out.track("es") == ["Bienvenidos a Nerdearla"]
    assert not any(t.refresh for t in worker.tracks)
    assert worker.set_glossary(worker.glossary) is False  # el mismo glosario: no reconecta
    assert not any(t.refresh for t in worker.tracks)
    assert worker.set_glossary([*worker.glossary, "Konex"]) is True
    assert all(t.refresh for t in worker.tracks)
    await worker.on_translation("es", " en el konex.")
    assert out.track("es") == ["Bienvenidos a Nerdearla en el Konex."]


async def test_pause_lag_measures_voice_to_text():
    worker, out = make_worker()
    now = time.time()
    worker.offsets.append(now - 0.8)  # el orador se calló hace 0,8 s
    await worker.on_original("That's a good point.", "en")
    assert 700 <= worker.latencies[-1] <= 1500
    # Si retomó antes de que llegara el texto, no se sabe a qué palabras corresponde: no se mide.
    worker.offsets.append(time.time() - 1.0)
    worker.onsets.append(time.time() - 0.5)
    before = len(worker.latencies)
    await worker.on_original("We didn't.", "en")
    assert len(worker.latencies) == before
