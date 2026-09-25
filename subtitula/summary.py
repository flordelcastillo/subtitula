""""¿Qué me perdí?": resumen en el idioma de quien lo pide de lo último que se dijo en una sala.

Lo hace Gemma 4 vía la API de Gemini (modelo abierto, sin costo en el plan actual) y, si no
responde, flash-lite. Se cachea por sala e idioma: aunque lo pida toda la sala a la vez, se
genera una sola vez por minuto.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from .captions import Caption
from .config import LANG_NAMES

log = logging.getLogger(__name__)

DEFAULT_MODELS = "gemma-4-26b-a4b-it,gemini-flash-lite-latest"
FRESH_S = 60


async def suggest_glossary(engine, name: str, speaker: str, topic: str, extra: str, current: list[str]) -> list[str]:
    """Términos que probablemente se digan en la charla y que un reconocedor podría escribir mal."""
    from google.genai import types

    prompt = (
        "A live captioning system needs a glossary for this conference talk.\n"
        f"Title: {name}\nSpeaker: {speaker or 'unknown'}\nTopic: {topic or 'unknown'}\n"
        + (f"Abstract or agenda text: {extra[:4000]}\n" if extra else "")
        + "List up to 25 terms that will probably be spoken and that a speech recognizer could misspell. "
        "Only proper nouns: people, companies, products, projects, programming languages, acronyms and "
        "commands, with their canonical spelling (for example Kubernetes, kubectl, PostgreSQL, ElevenLabs). "
        "Do NOT include common words or generic concepts (latency, multilingual, fine-tuning, open source, "
        "prompt engineering). One term per line, no numbering, no explanations.")
    config = types.GenerateContentConfig(temperature=0.2, max_output_tokens=400)
    _, resp = await engine._call(engine.translators, lambda m: ([prompt], config))
    seen = {t.lower() for t in current}
    terms = []
    for line in (resp.text or "").splitlines():
        term = line.strip().lstrip("-•*0123456789.) ").strip().strip('"')
        # Una palabra común con guion ("Fine-tuning", "Zero-shot") cambiaría texto normal: afuera.
        generic = "-" in term and term[1:] == term[1:].lower() and not any(c.isdigit() for c in term)
        if 1 < len(term) <= 40 and term.lower() not in seen and not generic:
            seen.add(term.lower())
            terms.append(term)
    return terms[:25]


class Summarizer:
    def __init__(self):
        self.engine = None
        self.cache: dict[tuple[str, str, int], tuple[float, dict]] = {}
        self.locks: dict[tuple[str, str, int], asyncio.Lock] = {}

    def _engine(self):
        if self.engine is None:
            from .engines.gemini import GeminiEngine

            self.engine = GeminiEngine(model=os.environ.get("SUBTITULA_SUMMARY_MODEL", DEFAULT_MODELS))
            self.engine.timeout_s = 25
        return self.engine

    async def summarize(self, sid: str, name: str, speaker: str, captions: list[Caption],
                        lang: str, minutes: int) -> dict:
        key = (sid, lang, minutes)
        cached = self.cache.get(key)
        if cached and time.time() - cached[0] < FRESH_S:
            return cached[1]
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self.cache.get(key)
            if cached and time.time() - cached[0] < FRESH_S:
                return cached[1]
            result = await self._generate(name, speaker, captions, lang, minutes)
            self.cache[key] = (time.time(), result)
            return result

    async def _generate(self, name: str, speaker: str, captions: list[Caption], lang: str, minutes: int) -> dict:
        from google.genai import types

        since = time.time() - minutes * 60
        # Se resume desde el original: es la versión más fiel de lo que se dijo.
        lines = [c.text for c in captions if c.created_at >= since and (c.original or not c.track) and c.text]
        if len(" ".join(lines)) < 80:
            return {"bullets": [], "empty": True, "generated_at": time.time(), "model": ""}
        target = LANG_NAMES.get(lang, "Español") if lang not in ("", "original") else "the language of the transcript"
        prompt = (
            f"This is the live transcript of the last {minutes} minutes of the conference talk \"{name}\""
            + (f" by {speaker}" if speaker else "") + ". Someone just arrived or got distracted.\n"
            f"Write 3 to 5 short bullet points in {target} with what was said, concrete and faithful to the "
            "transcript (no invented facts, keep technical terms as written). One bullet per line, starting "
            "with \"- \". Nothing else.\n\nTranscript:\n" + " ".join(lines)[-12000:])
        engine = self._engine()
        config = types.GenerateContentConfig(temperature=0.2, max_output_tokens=800)
        last: Exception | None = None
        # Orden de preferencia fijo (Gemma primero); si uno falla o no devuelve viñetas, el siguiente.
        for model in engine.translators.models:
            try:
                resp = await asyncio.wait_for(
                    engine.client.aio.models.generate_content(model=model, contents=[prompt], config=config),
                    timeout=8)
            except Exception as exc:  # noqa: BLE001
                last = exc
                log.info("resumen: %s no respondió (%s)", model, type(exc).__name__)
                continue
            bullets = [ln.strip().lstrip("-•* ").strip() for ln in (resp.text or "").splitlines()
                       if ln.strip().startswith(("-", "•", "*")) and len(ln.strip()) > 3]
            if bullets:
                return {"bullets": bullets[:5], "empty": False, "generated_at": time.time(), "model": model}
        raise RuntimeError(f"ningún modelo devolvió el resumen ({last})")
