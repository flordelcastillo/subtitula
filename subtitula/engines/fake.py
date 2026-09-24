"""Motor falso: no llama a ningún modelo. Sirve para tests, demos sin credenciales y pruebas de carga."""

from __future__ import annotations

import asyncio
import os
import random

from ..segmenter import Segment
from .base import Engine, EngineContext, EngineResult


class FakeEngine(Engine):
    name = "fake"

    def __init__(self, delay_s: float | None = None):
        # Simula la demora típica de una llamada a la API.
        self.delay_s = float(os.environ.get("SUBTITULA_FAKE_DELAY", "0.6")) if delay_s is None else delay_s
        self._n = 0

    async def process(self, segment: Segment, ctx: EngineContext) -> EngineResult:
        self._n += 1
        if self.delay_s:
            await asyncio.sleep(self.delay_s * random.uniform(0.7, 1.3))
        stamp = f"{segment.start:.1f}-{segment.end:.1f}s"
        base = f"{ctx.session_name} #{self._n} ({stamp})"
        tr = {lang: f"[{lang}] {base}" for lang in ctx.languages if lang != "en"}
        return EngineResult(lang="en", text=f"[en] {base}", tr=tr)
