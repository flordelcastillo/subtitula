"""Motor falso: no llama a ningún modelo. Sirve para tests, demos sin credenciales y pruebas de carga."""

from __future__ import annotations

import asyncio
import os
import random

from ..segmenter import Segment
from .base import Engine, EngineContext, EngineResult


class FakeEngine(Engine):
    name = "fake"

    def __init__(self, delay_s: float | None = None, two_stage: bool | None = None):
        # Simula la demora típica de una llamada a la API.
        self.delay_s = float(os.environ.get("SUBTITULA_FAKE_DELAY", "0.6")) if delay_s is None else delay_s
        self.two_stage = os.environ.get("SUBTITULA_FAKE_TWO_STAGE") == "1" if two_stage is None else two_stage
        self._n = 0

    async def translate(self, text: str, lang: str, ctx: EngineContext) -> EngineResult:
        if self.delay_s:
            await asyncio.sleep(self.delay_s * random.uniform(0.7, 1.3))
        base = text.removeprefix("[en] ")
        return EngineResult(lang="en", text=text, tr={t: f"[{t}] {base}" for t in ctx.languages if t != "en"})

    async def process(self, segment: Segment, ctx: EngineContext) -> EngineResult:
        self._n += 1
        if self.delay_s:
            await asyncio.sleep(self.delay_s * random.uniform(0.7, 1.3))
        stamp = f"{segment.start:.1f}-{segment.end:.1f}s"
        base = f"{ctx.session_name} #{self._n} ({stamp})"
        if self.two_stage:
            return EngineResult(lang="und", text=f"[en] {base}")
        tr = {lang: f"[{lang}] {base}" for lang in ctx.languages if lang != "en"}
        return EngineResult(lang="en", text=f"[en] {base}", tr=tr)
