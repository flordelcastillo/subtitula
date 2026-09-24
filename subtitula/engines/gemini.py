"""Motor Gemini, en dos etapas por defecto.

1. ASR: `gemini-3.5-transcribe` pasa el tramo a texto en ~2,5 s. El glosario entra como
   vocabulario del reconocedor y el modo SMART saca muletillas y repeticiones. El original se
   publica apenas vuelve.
2. Traducción: un modelo de texto traduce ese tramo (con el contexto previo y el glosario) a los
   idiomas del evento, y el subtítulo ya publicado se actualiza.

Separar las etapas hace que el original no espere a la traducción y que un modelo de texto
saturado demore sólo las traducciones. Cada etapa usa un pool de modelos: si uno da 429 (cuota)
o 503 (saturado) queda en espera y el pedido va al siguiente.

Con SUBTITULA_GEMINI_MODE=single se usa una sola llamada audio → JSON con transcripción y
traducciones, útil cuando los modelos flash-lite responden rápido.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

from google import genai
from google.genai import errors, types

from ..config import LANG_NAMES
from ..segmenter import Segment
from .base import Engine, EngineContext, EngineResult, pcm_to_wav

log = logging.getLogger(__name__)

DEFAULT_ASR = "gemini-3.5-transcribe"
# Modelos con cuotas separadas; Gemma queda al final como respaldo cuando los flash-lite saturan.
DEFAULT_TRANSLATE = "gemini-flash-lite-latest,gemini-3.1-flash-lite,gemma-4-26b-a4b-it"

SINGLE_SYSTEM = """You are a live conference captioner and simultaneous interpreter.
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

TRANSLATE_RULES = """You translate live subtitles of a technical conference talk.
The subtitle below is one short fragment; it may start or end mid-sentence. Translate only that
fragment, keeping it as a fragment, and do not add or complete anything.
Keep technical terms, product names, commands and acronyms as practitioners write them
(Kubernetes, kubectl, pull request, LLM). Use the glossary spelling. Write natural, concise subtitles.
Answer with exactly one line per requested field, in this format, and nothing else:"""


class ModelPool:
    """Round-robin entre modelos, salteando los que están en espera por cuota o saturación."""

    def __init__(self, spec: str):
        self.models = [m.strip() for m in spec.split(",") if m.strip()]
        self._next = 0
        self._cooldown: dict[str, float] = {}

    def pick(self) -> str:
        now = time.monotonic()
        for _ in range(len(self.models)):
            model = self.models[self._next % len(self.models)]
            self._next += 1
            if self._cooldown.get(model, 0) <= now:
                return model
        return min(self.models, key=lambda m: self._cooldown.get(m, 0))

    def rest(self, model: str, seconds: float) -> None:
        self._cooldown[model] = time.monotonic() + seconds

    def all_resting(self) -> bool:
        now = time.monotonic()
        return all(self._cooldown.get(m, 0) > now for m in self.models)

    def drop(self, model: str) -> None:
        if model in self.models and len(self.models) > 1:
            self.models.remove(model)


def _retry_after(exc: Exception, default: float) -> float:
    match = re.search(r"retry in ([\d.]+)s", str(exc))
    return float(match.group(1)) if match else default


class GeminiEngine(Engine):
    name = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key and not os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"):
            raise RuntimeError("Falta GEMINI_API_KEY (creala gratis en https://aistudio.google.com/apikey)")
        # Sin reintentos del SDK: ante un 429 o 503 conviene pasar a otro modelo, no esperar.
        http = types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))
        self.client = genai.Client(api_key=key, http_options=http) if key else genai.Client(http_options=http)
        self.mode = os.environ.get("SUBTITULA_GEMINI_MODE", "asr").lower()
        self.asr = ModelPool(os.environ.get("SUBTITULA_ASR_MODEL", DEFAULT_ASR))
        self.translators = ModelPool(model or os.environ.get("SUBTITULA_GEMINI_MODEL", DEFAULT_TRANSLATE))
        self.timeout_s = float(os.environ.get("SUBTITULA_GEMINI_TIMEOUT", "10"))
        self.two_stage = self.mode != "single"

    # -- llamada con failover ------------------------------------------------------------------

    async def _call(self, pool: ModelPool, build) -> tuple[str, types.GenerateContentResponse]:
        """`build(model)` devuelve (contents, config). Prueba modelos del pool hasta que uno responda."""
        last: Exception | None = None
        for _ in range(max(2, len(pool.models) + 1)):
            model = pool.pick()
            contents, config = build(model)
            try:
                resp = await asyncio.wait_for(
                    self.client.aio.models.generate_content(model=model, contents=contents, config=config),
                    timeout=self.timeout_s)
                return model, resp
            except errors.ClientError as exc:
                last = exc
                if exc.code == 404:
                    log.warning("%s no está disponible para esta clave; lo saco del pool", model)
                    pool.drop(model)
                    continue
                if exc.code == 429:
                    pool.rest(model, _retry_after(exc, 30))
                    log.warning("%s sin cuota; pruebo otro modelo", model)
                    if pool.all_resting():
                        raise
                    continue
                raise
            except (errors.ServerError, asyncio.TimeoutError) as exc:
                last = exc
                # Saturado o lento: se lo deja descansar un rato corto y se prueba otro.
                pool.rest(model, 15)
                log.warning("%s no respondió (%s); pruebo otro modelo", model, type(exc).__name__)
        raise last or RuntimeError("Gemini no respondió")

    @staticmethod
    def _usage(result: EngineResult, resp: types.GenerateContentResponse) -> None:
        usage = resp.usage_metadata
        if usage:
            result.input_tokens += usage.prompt_token_count or 0
            result.output_tokens += (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)

    # -- etapa 1: ASR --------------------------------------------------------------------------

    async def process(self, segment: Segment, ctx: EngineContext) -> EngineResult:
        if not self.two_stage:
            return await self._single(segment, ctx)
        audio = types.Part.from_bytes(data=pcm_to_wav(segment.pcm), mime_type="audio/wav")
        asr_cfg = types.AudioTranscriptionConfig(
            mode="SMART",
            custom_vocabulary=ctx.glossary[:100] or None,
            language_codes=[ctx.source_language] if ctx.source_language not in ("", "auto") else None,
        )
        config = types.GenerateContentConfig(audio_transcription_config=asr_cfg)
        model, resp = await self._call(self.asr, lambda m: ([audio], config))
        parts = resp.candidates[0].content.parts if resp.candidates and resp.candidates[0].content else []
        text = " ".join(p.audio_transcription.text.strip() for p in parts or []
                        if getattr(p, "audio_transcription", None) and p.audio_transcription.text).strip()
        if not text:
            text = (resp.text or "").strip() if any(getattr(p, "text", None) for p in parts or []) else ""
        lang = ctx.source_language if ctx.source_language not in ("", "auto") else "und"
        result = EngineResult(lang=lang, text=text, model=model)
        self._usage(result, resp)
        return result

    # -- etapa 2: traducción -------------------------------------------------------------------

    async def translate(self, text: str, lang: str, ctx: EngineContext) -> EngineResult:
        """Traduce un tramo ya transcripto. Devuelve el idioma detectado y las traducciones."""
        fields = ["LANG"] + [code.upper() for code in ctx.languages]
        lines = [TRANSLATE_RULES,
                 "LANG: <ISO 639-1 code of the subtitle's language>"]
        lines += [f"{code.upper()}: <{LANG_NAMES.get(code, code)} subtitle>" for code in ctx.languages]
        lines.append("")
        lines.append(f"Talk: {ctx.session_name}" + (f" by {ctx.speaker}" if ctx.speaker else ""))
        if ctx.glossary:
            lines.append("Glossary: " + ", ".join(ctx.glossary[:60]))
        if ctx.previous:
            lines.append("Previous fragments (context only, do not translate): " + " ".join(ctx.previous[-3:]))
        lines.append(f"Subtitle: {text}")
        prompt = "\n".join(lines)
        config = types.GenerateContentConfig(temperature=0.0, max_output_tokens=600)
        model, resp = await self._call(self.translators, lambda m: ([prompt], config))
        parsed = self._parse_lines(resp.text or "", fields)
        detected = (parsed.get("LANG") or lang or "und").lower()[:2]
        tr = {code: parsed[code.upper()] for code in ctx.languages
              if parsed.get(code.upper()) and code != detected}
        result = EngineResult(lang=detected, text=text, tr=tr, model=model)
        self._usage(result, resp)
        return result

    @staticmethod
    def _parse_lines(raw: str, fields: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        current = None
        for line in raw.replace("```", "").splitlines():
            match = re.match(r"^\s*\**\s*([A-Za-z]{2,4})\s*\**\s*:\s*(.*)$", line)
            if match and match.group(1).upper() in fields:
                current = match.group(1).upper()
                out[current] = match.group(2).strip().strip('"')
            elif current and line.strip():
                # Una traducción que el modelo partió en dos líneas.
                out[current] = f"{out[current]} {line.strip()}".strip()
        return out

    # -- modo de una sola llamada --------------------------------------------------------------

    def _schema(self, languages: list[str]) -> dict:
        props = {
            "lang": {"type": "string", "description": "ISO 639-1 code of the spoken language, e.g. en, es, pt"},
            "text": {"type": "string", "description": "Verbatim transcript in the spoken language"},
        }
        for lang in languages:
            props[f"text_{lang}"] = {"type": "string", "description": f"Subtitle in {LANG_NAMES.get(lang, lang)}"}
        return {"type": "object", "properties": props, "required": list(props)}

    def _single_prompt(self, ctx: EngineContext) -> str:
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

    async def _single(self, segment: Segment, ctx: EngineContext) -> EngineResult:
        audio = types.Part.from_bytes(data=pcm_to_wav(segment.pcm), mime_type="audio/wav")
        config = types.GenerateContentConfig(
            system_instruction=SINGLE_SYSTEM, temperature=0.0, response_mime_type="application/json",
            response_json_schema=self._schema(ctx.languages), max_output_tokens=1024)
        prompt = self._single_prompt(ctx)
        model, resp = await self._call(self.translators, lambda m: ([audio, prompt], config))
        result = self._parse_json(resp.text or "{}", ctx.languages)
        result.model = model
        self._usage(result, resp)
        return result

    @staticmethod
    def _parse_json(raw: str, languages: list[str]) -> EngineResult:
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
