"""Worker de una sesión (un escenario): fuente → segmentador → motor → publicación en orden."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import Protocol

import httpx
import numpy as np

from .audio import QueueSource, ffmpeg_pcm, is_live
from .captions import Caption
from .config import SessionConfig
from .engines import Engine, EngineContext
from .segmenter import Segment, Segmenter, SegmenterConfig, frame_dbfs

log = logging.getLogger(__name__)


class Publisher(Protocol):
    async def caption(self, caption: Caption) -> int | None: ...
    async def status(self, session: str, status: dict) -> dict | None: ...


class HttpPublisher:
    """Publica en un hub remoto: permite correr cada escenario en otra máquina o contenedor."""

    def __init__(self, hub_url: str, token: str = ""):
        self.hub_url = hub_url.rstrip("/")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.http = httpx.AsyncClient(timeout=5, headers=headers)

    async def _post(self, session: str, payload: dict) -> dict | None:  # noqa: C901
        for attempt in range(3):
            try:
                resp = await self.http.post(f"{self.hub_url}/api/ingest/{session}", json=payload)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as exc:
                if attempt == 2:
                    log.warning("No pude publicar en el hub: %s", exc)
                await asyncio.sleep(0.3 * (attempt + 1))
        return None

    async def caption(self, caption: Caption) -> int | None:
        reply = await self._post(caption.session, {"type": "caption", "caption": caption.to_dict()})
        return reply.get("seq") if reply else None

    async def status(self, session: str, status: dict) -> dict | None:
        return await self._post(session, {"type": "status", "status": status})


class SessionWorker:
    MAX_INFLIGHT = 3
    MAX_BACKLOG = 8
    MAX_TRANSLATIONS = 4

    def __init__(self, session: SessionConfig, engine: Engine, publisher: Publisher,
                 languages: list[str], glossary: list[str],
                 source_factory: Callable[[], AsyncIterator[bytes]] | None = None,
                 seg_cfg: SegmenterConfig | None = None):
        self.session = session
        self.engine = engine
        self.publisher = publisher
        self.languages = languages
        self.glossary = list(dict.fromkeys([*glossary, *session.glossary]))
        self.queue_source = QueueSource() if session.source == "browser" else None
        self.backpressure = not session.realtime and not is_live(session.source)
        self._source_factory = source_factory
        self.segmenter = Segmenter(seg_cfg)
        self.seq = 0
        self.previous: deque[str] = deque(maxlen=3)
        self.latencies: deque[int] = deque(maxlen=60)
        self.tr_latencies: deque[int] = deque(maxlen=60)
        self.tr_pending = 0
        self._tr_sem = asyncio.Semaphore(self.MAX_TRANSLATIONS)
        self._tr_tasks: set[asyncio.Task] = set()
        self.state = "idle"
        self.last_error = ""
        self.errors = 0
        self.dropped = 0
        self.segments = 0
        self.captions = 0
        self.audio_seconds = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.level_dbfs = -120.0
        self.last_audio_at = 0.0
        self.started_at = time.time()
        self._pending: asyncio.Queue[asyncio.Task | None] = asyncio.Queue()
        self._sem = asyncio.Semaphore(self.MAX_INFLIGHT)
        self._stop = asyncio.Event()

    # -- ciclo de vida -------------------------------------------------------------------------

    def _source(self) -> AsyncIterator[bytes]:
        if self._source_factory:
            return self._source_factory()
        if self.queue_source:
            return self.queue_source.__aiter__()
        return ffmpeg_pcm(self.session.source, self.session.realtime, self.session.loop)

    async def run(self) -> None:
        emitter = asyncio.create_task(self._emit_in_order())
        heartbeat = asyncio.create_task(self._heartbeat())
        backoff = 1.0
        try:
            while not self._stop.is_set():
                self.state = "connecting"
                try:
                    async for pcm in self._source():
                        if self.state != "live":
                            self.state = "live"
                            backoff = 1.0
                        self._on_audio(pcm)
                        for seg in self.segmenter.feed(pcm):
                            await self._schedule(seg)
                        if self._stop.is_set():
                            break
                    for seg in self.segmenter.flush():
                        await self._schedule(seg)
                    # Un archivo que terminó no se reintenta; un vivo que se cortó sí.
                    if not is_live(self.session.source) or self._source_factory:
                        self.state = "ended"
                        break
                    raise RuntimeError("la fuente se cortó")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - un escenario no puede tirar abajo el resto
                    self.errors += 1
                    self.last_error = str(exc)[:300]
                    self.state = "reconnecting"
                    log.warning("[%s] fuente caída: %s (reintento en %.0fs)", self.session.id, exc, backoff)
                    await self._publish_status()
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                    except asyncio.TimeoutError:
                        pass
                    backoff = min(backoff * 2, 30)
        finally:
            await self._pending.put(None)
            await emitter
            if self._tr_tasks:
                await asyncio.gather(*self._tr_tasks, return_exceptions=True)
            heartbeat.cancel()
            if self.state not in ("ended",):
                self.state = "stopped"
            await self._publish_status()

    def stop(self) -> None:
        self._stop.set()

    # -- procesamiento -------------------------------------------------------------------------

    def _on_audio(self, pcm: bytes) -> None:
        self.audio_seconds += len(pcm) / 32000
        self.last_audio_at = time.time()
        samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype=np.int16)
        self.level_dbfs = round(frame_dbfs(samples), 1)

    async def _schedule(self, seg: Segment) -> None:
        self.segments += 1
        # Un archivo leído a toda velocidad espera al motor; un vivo no puede esperar.
        while self.backpressure and self._pending.qsize() >= self.MAX_BACKLOG:
            await asyncio.sleep(0.05)
        if self._pending.qsize() >= self.MAX_BACKLOG:
            # Si el motor no da abasto conviene saltear un tramo antes que acumular minutos de atraso.
            self.dropped += 1
            log.warning("[%s] backlog lleno, descarto el tramo %.1f-%.1f", self.session.id, seg.start, seg.end)
            return
        ready_at = time.time()
        self._pending.put_nowait(asyncio.create_task(self._process(seg, ready_at)))

    def _context(self) -> EngineContext:
        s = self.session
        return EngineContext(session_name=s.name, languages=self.languages, source_language=s.language,
                             glossary=self.glossary, speaker=s.speaker, topic=s.topic,
                             previous=list(self.previous))

    async def _retrying(self, call, what: str):
        """En vivo, un fallo se saltea. Leyendo un archivo, se espera y se reintenta (cuota, saturación)."""
        attempts = 8 if self.backpressure else 1
        for attempt in range(attempts):
            try:
                return await call()
            except Exception as exc:  # noqa: BLE001
                if attempt == attempts - 1:
                    raise
                wait = min(10 * (attempt + 1), 45)
                log.warning("[%s] %s falló (%s); reintento en %ds", self.session.id, what, type(exc).__name__, wait)
                await asyncio.sleep(wait)

    async def _process(self, seg: Segment, ready_at: float):
        async with self._sem:
            try:
                result = await self._retrying(lambda: self.engine.process(seg, self._context()),
                                              f"el tramo {seg.start:.1f}-{seg.end:.1f}")
                return seg, ready_at, result
            except Exception as exc:  # noqa: BLE001
                self.errors += 1
                self.last_error = f"{type(exc).__name__}: {str(exc)[:250]}"
                log.warning("[%s] el motor falló en %.1f-%.1f: %s", self.session.id, seg.start, seg.end, exc)
                return seg, ready_at, None

    async def _emit_in_order(self) -> None:
        while True:
            task = await self._pending.get()
            if task is None:
                return
            seg, ready_at, result = await task
            if result is None or not result.text:
                continue
            now = time.time()
            latency = int((now - ready_at) * 1000)
            self.latencies.append(latency)
            self.seq += 1
            self.captions += 1
            context = self._context()
            self.previous.append(result.text)
            self.input_tokens += result.input_tokens
            self.output_tokens += result.output_tokens
            translate = self.engine.two_stage and any(lang != result.lang for lang in self.languages)
            cap = Caption(session=self.session.id, seq=self.seq, start=round(seg.start, 2),
                          end=round(seg.end, 2), lang=result.lang, text=result.text, tr=result.tr,
                          latency_ms=latency, created_at=now, pending=translate)
            assigned = await self.publisher.caption(cap)
            if assigned:
                cap.seq = assigned
            if translate:
                task = asyncio.create_task(self._translate(cap, ready_at, context))
                self._tr_tasks.add(task)
                task.add_done_callback(self._tr_tasks.discard)

    async def _translate(self, cap: Caption, ready_at: float, ctx: EngineContext) -> None:
        self.tr_pending += 1
        try:
            async with self._tr_sem:
                result = await self._retrying(lambda: self.engine.translate(cap.text, cap.lang, ctx),
                                              f"la traducción del #{cap.seq}")
            cap.lang = result.lang if result.lang != "und" else cap.lang
            cap.tr = result.tr
            cap.tr_latency_ms = int((time.time() - ready_at) * 1000)
            self.tr_latencies.append(cap.tr_latency_ms)
            self.input_tokens += result.input_tokens
            self.output_tokens += result.output_tokens
        except Exception as exc:  # noqa: BLE001
            self.errors += 1
            self.last_error = f"traducción: {type(exc).__name__}: {str(exc)[:230]}"
            log.warning("[%s] no se pudo traducir el #%d: %s", self.session.id, cap.seq, exc)
        finally:
            self.tr_pending -= 1
            # Se publica aunque falle: así la vista deja de esperar y muestra el original.
            cap.pending = False
            await self.publisher.caption(cap)

    # -- estado --------------------------------------------------------------------------------

    def status(self) -> dict:
        lat = sorted(self.latencies)
        return {
            "state": self.state,
            "engine": self.engine.name,
            "source": "browser" if self.queue_source else self.session.source,
            "uptime_s": round(time.time() - self.started_at),
            "audio_s": round(self.audio_seconds, 1),
            "level_dbfs": self.level_dbfs,
            "silent_for_s": round(time.time() - self.last_audio_at, 1) if self.last_audio_at else None,
            "segments": self.segments,
            "captions": self.captions,
            "dropped": self.dropped,
            "errors": self.errors,
            "last_error": self.last_error,
            "inflight": self._pending.qsize(),
            "latency_p50_ms": lat[len(lat) // 2] if lat else None,
            "latency_p90_ms": lat[int(len(lat) * 0.9)] if lat else None,
            "translation_p50_ms": sorted(self.tr_latencies)[len(self.tr_latencies) // 2] if self.tr_latencies else None,
            "translation_p90_ms": sorted(self.tr_latencies)[int(len(self.tr_latencies) * 0.9)] if self.tr_latencies else None,
            "translations_pending": self.tr_pending,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "updated_at": time.time(),
        }

    def set_glossary(self, terms: list[str]) -> None:
        self.glossary = list(dict.fromkeys(terms))

    async def _publish_status(self) -> None:
        try:
            reply = await self.publisher.status(self.session.id, self.status())
        except Exception as exc:  # noqa: BLE001
            log.debug("status no publicado: %s", exc)
            return
        # El hub devuelve el glosario vigente: así una corrección hecha en el panel llega a
        # workers que corren en otra máquina sin reiniciarlos.
        if reply and isinstance(reply.get("glossary"), list):
            self.set_glossary(reply["glossary"])

    async def _heartbeat(self) -> None:
        while True:
            await self._publish_status()
            await asyncio.sleep(2)
