"""Motor 100% local: faster-whisper transcribe y Gemma (vía Ollama) traduce.

Sin Ollama configurado, sólo se traduce a inglés con la tarea "translate" de Whisper.
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np

from ..config import LANG_NAMES
from ..segmenter import Segment
from .base import Engine, EngineContext, EngineResult

log = logging.getLogger(__name__)


class LocalEngine(Engine):
    name = "local"

    def __init__(self):
        from faster_whisper import WhisperModel  # dependencia opcional: pip install .[local]

        model = os.environ.get("SUBTITULA_WHISPER_MODEL", "small")
        device = os.environ.get("SUBTITULA_WHISPER_DEVICE", "auto")
        compute = os.environ.get("SUBTITULA_WHISPER_COMPUTE", "int8")
        self.whisper = WhisperModel(model, device=device, compute_type=compute)
        self.ollama_url = os.environ.get("OLLAMA_URL", "").rstrip("/")
        self.ollama_model = os.environ.get("SUBTITULA_OLLAMA_MODEL", "gemma3:4b")
        # Whisper no es thread-safe para llamadas simultáneas sobre el mismo modelo en CPU.
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.http = httpx.AsyncClient(timeout=20)

    def _transcribe(self, audio: np.ndarray, ctx: EngineContext, task: str) -> tuple[str, str]:
        lang = None if ctx.source_language in ("", "auto") else ctx.source_language
        prompt = ", ".join(ctx.glossary[:40]) or None
        segments, info = self.whisper.transcribe(
            audio, language=lang, task=task, beam_size=1, vad_filter=False,
            initial_prompt=prompt, condition_on_previous_text=False)
        return info.language, " ".join(s.text.strip() for s in segments).strip()

    async def _translate(self, text: str, src: str, dst: str, ctx: EngineContext) -> str:
        prompt = (
            f"Translate this live conference subtitle from {LANG_NAMES.get(src, src)} to "
            f"{LANG_NAMES.get(dst, dst)}. Keep technical terms as practitioners write them. "
            f"Glossary: {', '.join(ctx.glossary[:40])}. Reply with the translation only.\n\n{text}")
        resp = await self.http.post(f"{self.ollama_url}/api/generate", json={
            "model": self.ollama_model, "prompt": prompt, "stream": False,
            "options": {"temperature": 0}})
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    async def process(self, segment: Segment, ctx: EngineContext) -> EngineResult:
        audio = np.frombuffer(segment.pcm, dtype=np.int16).astype(np.float32) / 32768.0
        loop = asyncio.get_running_loop()
        lang, text = await loop.run_in_executor(self.pool, self._transcribe, audio, ctx, "transcribe")
        tr: dict[str, str] = {}
        if not text:
            return EngineResult(lang=lang, text="")
        targets = [t for t in ctx.languages if t != lang]
        if self.ollama_url:
            results = await asyncio.gather(
                *(self._translate(text, lang, t, ctx) for t in targets), return_exceptions=True)
            for target, value in zip(targets, results):
                if isinstance(value, str) and value:
                    tr[target] = value
                elif isinstance(value, Exception):
                    log.warning("Ollama falló traduciendo a %s: %s", target, value)
        elif "en" in targets:
            _, english = await loop.run_in_executor(self.pool, self._transcribe, audio, ctx, "translate")
            if english:
                tr["en"] = english
        return EngineResult(lang=lang, text=text, tr=tr)

    async def close(self) -> None:
        await self.http.aclose()
        self.pool.shutdown(wait=False)
