"""Motor Gemini: una sola llamada por tramo devuelve transcripción + traducciones.

Hacer las dos cosas en la misma llamada tiene tres ventajas frente a transcribir y después
traducir el texto: la mitad de latencia, la traducción ve el audio (tono, énfasis, nombres
pronunciados) y el glosario se aplica igual en el original y en la traducción.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from google import genai
from google.genai import errors, types

from ..config import LANG_NAMES
from ..segmenter import Segment
from .base import Engine, EngineContext, EngineResult, pcm_to_wav

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-flash-lite-latest"

SYSTEM = """You are a live conference captioner and simultaneous interpreter.
You receive a short audio clip (a few seconds) cut from a live technical talk.
Return exactly what is said in the clip, then translate it.

Rules:
- Transcribe verbatim in the spoken language, with punctuation. Drop filler sounds (uh, eh, este, ehm).
- The clip may start or end mid-sentence: transcribe only the words in THIS clip and do not complete
  or repeat the previous context. The previous context is only there to resolve names and meaning.
- If the clip has no intelligible speech (silence, music, applause, noise) return empty strings.
- Keep technical terms, product names, code identifiers, commands and acronyms as they are usually
  written by practitioners (Kubernetes, kubectl, PostgreSQL, LLM, pull request). Do not translate them.
- Translations must be natural subtitles a native speaker would write, concise, same meaning.
- Use the glossary spelling whenever a glossary term is spoken.
"""


class GeminiEngine(Engine):
    name = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key and not os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"):
            raise RuntimeError("Falta GEMINI_API_KEY (creala gratis en https://aistudio.google.com/apikey)")
        self.client = genai.Client(api_key=key) if key else genai.Client()
        self.model = model or os.environ.get("SUBTITULA_GEMINI_MODEL", DEFAULT_MODEL)
        self.timeout_s = float(os.environ.get("SUBTITULA_GEMINI_TIMEOUT", "12"))
        # Los modelos sin razonamiento configurable rechazan thinking_config: se apaga al primer 400.
        self._thinking = True

    def _schema(self, languages: list[str]) -> dict:
        props = {
            "lang": {"type": "string", "description": "ISO 639-1 code of the spoken language, e.g. en, es, pt"},
            "text": {"type": "string", "description": "Verbatim transcript in the spoken language"},
        }
        for lang in languages:
            props[f"text_{lang}"] = {"type": "string", "description": f"Subtitle in {LANG_NAMES.get(lang, lang)}"}
        return {"type": "object", "properties": props, "required": list(props)}

    def _prompt(self, ctx: EngineContext) -> str:
        parts = [f"Talk: {ctx.session_name}"]
        if ctx.speaker:
            parts.append(f"Speaker: {ctx.speaker}")
        if ctx.topic:
            parts.append(f"Topic: {ctx.topic}")
        if ctx.source_language not in ("", "auto"):
            parts.append(f"Expected spoken language: {LANG_NAMES.get(ctx.source_language, ctx.source_language)}"
                         " (the audience may ask questions in another language).")
        if ctx.glossary:
            parts.append("Glossary: " + ", ".join(ctx.glossary))
        if ctx.previous:
            parts.append("Previous context (already captioned, do not repeat): " + " ".join(ctx.previous[-3:]))
        targets = ", ".join(f"text_{lang} = {LANG_NAMES.get(lang, lang)}" for lang in ctx.languages)
        parts.append(f"Fill {targets}. For the field matching the spoken language, copy the transcript.")
        return "\n".join(parts)

    def _config(self, languages: list[str]) -> types.GenerateContentConfig:
        kwargs = dict(
            system_instruction=SYSTEM,
            temperature=0.0,
            response_mime_type="application/json",
            response_json_schema=self._schema(languages),
            max_output_tokens=1024,
        )
        if self._thinking:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        return types.GenerateContentConfig(**kwargs)

    async def process(self, segment: Segment, ctx: EngineContext) -> EngineResult:
        audio = types.Part.from_bytes(data=pcm_to_wav(segment.pcm), mime_type="audio/wav")
        contents = [audio, self._prompt(ctx)]
        for attempt in range(3):
            try:
                resp = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self.model, contents=contents, config=self._config(ctx.languages)),
                    timeout=self.timeout_s,
                )
                result = self._parse(resp.text or "{}", ctx.languages)
                usage = resp.usage_metadata
                if usage:
                    result.input_tokens = usage.prompt_token_count or 0
                    result.output_tokens = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                return result
            except errors.ClientError as exc:
                if self._thinking and exc.code == 400 and "thinking" in str(exc).lower():
                    log.info("El modelo %s no acepta thinking_budget=0; sigo sin configurarlo", self.model)
                    self._thinking = False
                    continue
                if exc.code == 429 and attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise
            except (errors.ServerError, asyncio.TimeoutError):
                if attempt < 2:
                    continue
                raise
        raise RuntimeError("Gemini no respondió")

    @staticmethod
    def _parse(raw: str, languages: list[str]) -> EngineResult:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Ante un JSON cortado se usa el texto crudo antes que perder el subtítulo.
            return EngineResult(lang="und", text=raw.strip())
        lang = (data.get("lang") or "und").lower()[:2]
        text = (data.get("text") or "").strip()
        tr = {}
        for target in languages:
            value = (data.get(f"text_{target}") or "").strip()
            if value and target != lang:
                tr[target] = value
        return EngineResult(lang=lang, text=text, tr=tr)
