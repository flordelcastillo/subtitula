"""Motor de interpretación simultánea con la Gemini Live API (`gemini-live`).

Cada sala abre una sesión de `gemini-3.5-live-translate-preview` por idioma de destino y le
manda el audio en vivo. Cada sesión devuelve, palabra por palabra, la transcripción del original
y la traducción. Con eso se arman líneas de subtítulo que crecen en pantalla mientras la persona
habla, en lugar de esperar a que termine cada tramo.

Una sesión abierta no consume un pedido por tramo, así que no choca con el límite de pedidos
por minuto. Si una sesión se corta, se reabre retomando el contexto (session resumption).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import deque

from google import genai
from google.genai import types

from .captions import Caption
from .engines import Engine, EngineContext
from .glossary import canonical_terms
from .worker import SessionWorker

log = logging.getLogger(__name__)

DEFAULT_LIVE_MODEL = "gemini-3.5-live-translate-preview"
SENTENCE_END = re.compile(r"[.?!…。]\s*$")
SENTENCE_SPLIT = re.compile(r"(?<=[.?!…。])(?=\s)")
CLAUSE_END = re.compile(r"[,;:]\s*$")
MAX_LINE_CHARS = 84  # dos renglones de 42, la norma de subtitulado
LINE_GAP_S = 2.0  # sin palabras nuevas durante este tiempo, la línea se cierra


class LiveEngine(Engine):
    """Marcador para elegir el worker en vivo; la conexión la maneja LiveTrack."""

    name = "gemini-live"

    def __init__(self):
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("Falta GEMINI_API_KEY (creala en https://aistudio.google.com/apikey)")
        self.client = genai.Client(api_key=key)
        self.model = os.environ.get("SUBTITULA_LIVE_MODEL", DEFAULT_LIVE_MODEL)

    async def process(self, segment, ctx: EngineContext):  # pragma: no cover - no se usa por tramo
        raise NotImplementedError("gemini-live trabaja en streaming, no por tramos")


class LiveTrack:
    """Una sesión Live hacia un idioma de destino. Reconecta sola si se corta."""

    def __init__(self, worker: "LiveSessionWorker", target: str, primary: bool):
        self.worker = worker
        self.target = target
        self.primary = primary  # sólo una sesión aporta el texto original
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=100)
        self.handle: str | None = None
        self.connected = False
        self.reconnects = 0
        # Idiomas bajo demanda: una sesión sin público se cierra y se reabre cuando alguien la pide.
        self.wanted = asyncio.Event()
        self.wanted.set()
        self.refresh = False  # el glosario cambió: reconectar ya, con el vocabulario nuevo
        self.fresh = False  # el vigía la cortó por atraso: reabrir sin retomar ni arrastrar audio viejo
        self.has_audio = asyncio.Event()  # no se abre sesión hasta que llega audio (salas de navegador)
        self.connected_at = 0.0
        self.last_in_at = 0.0
        self.last_out_at = 0.0
        self.last_cut_at = 0.0
        self.chars_at_out = 0  # cuánto original había llegado cuando salió la última traducción
        self.lag_cuts = 0

    def put(self, pcm: bytes | None) -> None:
        if pcm is not None and not self.wanted.is_set():
            return
        if pcm is not None:
            self.has_audio.set()
        try:
            self.queue.put_nowait(pcm)
        except asyncio.QueueFull:
            # Si la sesión se atrasa (reconectando), se descarta audio viejo: el vivo manda.
            self.queue.get_nowait()
            self.queue.put_nowait(pcm)

    def _config(self) -> types.LiveConnectConfig:
        session = self.worker.session
        asr = types.AudioTranscriptionConfig(
            custom_vocabulary=canonical_terms(self.worker.glossary)[:100] or None,
            language_codes=[session.language] if session.language not in ("", "auto") else None,
        )
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            input_audio_transcription=asr,
            output_audio_transcription=types.AudioTranscriptionConfig(),
            # Si alguien habla directamente en el idioma de destino (preguntas del público), se repite tal cual.
            translation_config=types.TranslationConfig(target_language_code=self.target, echo_target_language=True),
            session_resumption=types.SessionResumptionConfig(handle=self.handle),
            context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()),
        )

    async def run(self) -> None:
        engine: LiveEngine = self.worker.engine  # type: ignore[assignment]
        backoff = 1.0
        while not self.worker.stopping:
            await self.wanted.wait()
            await self.has_audio.wait()
            self.refresh = False  # la conexión nueva ya toma el glosario vigente
            released = False
            try:
                async with engine.client.aio.live.connect(model=engine.model, config=self._config()) as session:
                    self.connected = True
                    self.connected_at = time.time()
                    backoff = 1.0
                    sender = asyncio.create_task(self._send(session))
                    receiver = asyncio.create_task(self._receive(session))
                    idle = asyncio.create_task(self._until_unwanted())
                    try:
                        done, _ = await asyncio.wait({receiver, idle}, return_when=asyncio.FIRST_COMPLETED)
                        released = idle in done
                        if receiver in done:
                            receiver.result()  # propaga el error de la sesión, si lo hubo
                    finally:
                        for task in (sender, receiver, idle):
                            task.cancel()
                        self.connected = False
                if self.worker.stopping:
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - una sesión caída no tira abajo la sala
                self.connected = False
                self.worker.errors += 1
                self.worker.last_error = f"sesión {self.target}: {type(exc).__name__}: {str(exc)[:200]}"
                log.warning("[%s/%s] sesión Live caída: %s", self.worker.session.id, self.target, exc)
                # Un identificador de retome vencido haría fallar cada reintento: se abre una sesión nueva.
                self.handle = None
            if self.worker.stopping:
                return
            if released and self.fresh and self.wanted.is_set():
                # Cortada por atraso: sesión nueva, sin contexto viejo ni audio acumulado.
                self.fresh = self.refresh = False
                self.handle = None
                while not self.queue.empty():
                    self.queue.get_nowait()
                self.worker.builders[self.target].close()
                if self.primary:
                    self.worker.original.close()
                continue
            if released and self.refresh and self.wanted.is_set():
                self.refresh = False
                log.info("[%s/%s] glosario nuevo: reconecto retomando el contexto", self.worker.session.id, self.target)
                continue
            if released:
                # Se cerró por falta de público: no es un error ni una reconexión.
                log.info("[%s/%s] sin público, sesión en espera", self.worker.session.id, self.target)
                self.worker.builders[self.target].close()
                self.handle = None
                while not self.queue.empty():  # al reabrir, nada de audio viejo
                    self.queue.get_nowait()
                continue
            self.reconnects += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 15)

    async def _until_unwanted(self) -> None:
        while self.wanted.is_set() and not self.refresh:
            await asyncio.sleep(0.5)

    async def _send(self, session) -> None:
        while True:
            pcm = await self.queue.get()
            if pcm is None:
                await session.send_realtime_input(audio_stream_end=True)
                return
            await session.send_realtime_input(audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000"))

    async def _receive(self, session) -> None:
        async for msg in session.receive():
            if msg.session_resumption_update and msg.session_resumption_update.new_handle:
                self.handle = msg.session_resumption_update.new_handle
            if msg.usage_metadata:
                self.worker.add_usage(self.worker.engine.model, msg.usage_metadata.prompt_token_count or 0,
                                      msg.usage_metadata.response_token_count or 0)
            if msg.go_away:
                log.info("[%s/%s] el servidor pidió reconectar", self.worker.session.id, self.target)
                return
            sc = msg.server_content
            if not sc:
                continue
            if self.primary and sc.input_transcription and sc.input_transcription.text:
                self.last_in_at = time.time()
                await self.worker.on_original(sc.input_transcription.text, sc.input_transcription.language_code)
            if sc.output_transcription and sc.output_transcription.text:
                self.last_out_at = time.time()
                self.chars_at_out = self.worker.original_chars
                await self.worker.on_translation(self.target, sc.output_transcription.text)
            # La sesión también devuelve la interpretación hablada: se reparte a quien la escucha.
            if sc.model_turn:
                for part in sc.model_turn.parts or []:
                    blob = part.inline_data
                    if blob and blob.data and (blob.mime_type or "").startswith("audio/pcm"):
                        rate = re.search(r"rate=(\d+)", blob.mime_type or "")
                        self.worker.on_speech(self.target, blob.data, int(rate.group(1)) if rate else 24000)


class TrackBuilder:
    """Arma las líneas de una pista (el original o un idioma de destino) a partir de fragmentos.

    Una línea se cierra al terminar una oración, en una coma si ya es larga, al llegar a 84
    caracteres o tras una pausa. Cada idioma corta con su propia puntuación: así el español se lee
    como español y no como inglés partido en los lugares del inglés.
    """

    def __init__(self, worker: "LiveSessionWorker", track: str, original: bool):
        self.worker = worker
        self.track = track
        self.original = original
        self.current: Caption | None = None
        self.first_at = 0.0  # cuándo llegó el primer fragmento de la línea abierta
        self.last_at = 0.0
        self.last_end = 0.0
        self.last_lag_ms = 0
        self.last_lag_at = 0.0

    async def add(self, delta: str, lang: str) -> None:
        # Un fragmento puede traer el final de una oración y el comienzo de otra: se corta ahí.
        pieces = [p for p in SENTENCE_SPLIT.split(delta) if p]
        for i, piece in enumerate(pieces):
            if i > 0 and not piece[:1].isspace():
                piece = " " + piece
            if self.current is not None and len(self.current.text) + len(piece) > MAX_LINE_CHARS:
                self.close()
            await self._add(piece, lang)

    async def _add(self, delta: str, lang: str) -> None:
        w = self.worker
        now = time.time()
        if self.current is None:
            w.seq += 1
            if self.original:
                w.captions += 1
            # El texto llega ~2 s detrás de la voz: el subtítulo empieza antes que el evento,
            # pero nunca antes de que termine la línea anterior de la misma pista.
            start = max(self.last_end, w._audio_pos() - 2.5)
            self.current = Caption(session=w.session.id, seq=w.seq, start=start, end=w._audio_pos(),
                                   lang=lang, text="", created_at=now, track=self.track, original=self.original)
            self.first_at = now
        cap = self.current
        cap.text = w.fixer.fix(_join(cap.text, delta))
        cap.end = w._audio_pos()
        self.last_at = now
        size = len(cap.text)
        done = ((SENTENCE_END.search(cap.text) and size >= 15) or (CLAUSE_END.search(cap.text) and size >= 60)
                or size >= MAX_LINE_CHARS)
        await w._publish(cap)
        if done:
            self.close()

    def close(self) -> None:
        if self.current is not None:
            lag = self.worker._pause_lag(self.last_at)
            if lag:
                self.last_lag_ms, self.last_lag_at = lag, self.last_at
                self.current.latency_ms = lag
                (self.worker.latencies if self.original else self.worker.tr_latencies).append(lag)
            self.last_end = self.current.end
            self.current = None

    def idle(self, now: float) -> bool:
        return self.current is not None and now - self.last_at > LINE_GAP_S


class LiveSessionWorker(SessionWorker):
    """Worker de una sala con la Live API: el audio va directo a las sesiones, sin tramos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # En vivo el audio siempre va a velocidad real: la Live API espera una charla, no un archivo.
        self.session.realtime = True
        self.backpressure = False
        self.source_lang = self.session.language if self.session.language not in ("", "auto") else ""
        targets = [lang for lang in self.languages if lang != self.source_lang] or self.languages[:1]
        self.tracks = [LiveTrack(self, lang, primary=i == 0) for i, lang in enumerate(targets)]
        # Con idioma conocido, la pista original es la de ese idioma (quien elige "en" en una charla
        # en inglés lee el original); con "auto" es una pista aparte.
        self.original = TrackBuilder(self, self.source_lang or "original", original=True)
        self.builders = {t.target: TrackBuilder(self, t.target, original=False) for t in self.tracks}
        self.onsets: deque[float] = deque(maxlen=40)
        self.offsets: deque[float] = deque(maxlen=40)
        self._quiet_chunks = 0
        self.stopping = False
        self._lock = asyncio.Lock()
        # Silencio largo (cortes, cambio de orador): no se manda audio, la Live API cobra por segundo.
        self.silence_dbfs = float(os.environ.get("SUBTITULA_SILENCE_DBFS", "-50"))
        self.pause_after_s = float(os.environ.get("SUBTITULA_PAUSE_AFTER_S", "10"))
        self._silent_s = 0.0
        self.paused = False
        self.saved_audio_s = 0.0
        self._preroll: deque[bytes] = deque(maxlen=5)  # 0,5 s para no comerse la primera sílaba
        # Idiomas bajo demanda: fuera del principal, una sesión se cierra tras LINGER_S sin público.
        self.on_demand = os.environ.get("SUBTITULA_ON_DEMAND", "1") != "0"
        self.linger_s = float(os.environ.get("SUBTITULA_LINGER_S", "120"))
        self.demand_until: dict[str, float] = {}
        # Vigía: nunca quedar atrasado. Mejor cortar y retomar en vivo que acumular segundos de atraso.
        self.stall_s = float(os.environ.get("SUBTITULA_STALL_S", "10"))
        self.startup_s = float(os.environ.get("SUBTITULA_STARTUP_S", "6"))
        self.stall_chars = int(os.environ.get("SUBTITULA_STALL_CHARS", "150"))  # ~2 líneas de original sin traducir
        self.original_chars = 0
        self.max_lag_ms = int(float(os.environ.get("SUBTITULA_MAX_LAG_S", "6")) * 1000)
        self.voice: deque[float] = deque(maxlen=400)  # momentos (cada 100 ms) con voz en el audio

    # -- demanda y silencio ----------------------------------------------------------------------

    def set_demand(self, langs: list[str]) -> None:
        """El hub informa qué idiomas está mirando o escuchando alguien en esta sala."""
        if not self.on_demand:
            return
        now = time.time()
        for lang in langs:
            self.demand_until[lang] = now + self.linger_s
        grace = now - self.started_at < self.linger_s  # al arrancar, todo abierto un rato
        for track in self.tracks:
            if track.primary:
                continue  # de la sesión principal sale el original: siempre abierta
            if grace or self.demand_until.get(track.target, 0) > now:
                track.wanted.set()
            else:
                track.wanted.clear()

    def _forward(self, pcm: bytes) -> None:
        chunk_s = len(pcm) / 32000
        if self.level_dbfs < self.silence_dbfs:
            self._silent_s += chunk_s
        else:
            self._silent_s = 0.0
            self.voice.append(time.time())
        if self._silent_s > self.pause_after_s:
            self.paused = True
            self.saved_audio_s += chunk_s * len(self.tracks)
            self._preroll.append(pcm)
            return
        if self.paused:
            self.paused = False
            for old in self._preroll:
                for track in self.tracks:
                    track.put(old)
            self._preroll.clear()
        for track in self.tracks:
            track.put(pcm)

    # -- audio ---------------------------------------------------------------------------------

    def _on_audio(self, pcm: bytes) -> None:
        super()._on_audio(pcm)
        # Pausas y reanudaciones del orador (≥300 ms de silencio) para medir la demora del texto.
        now = time.time()
        if self.level_dbfs < -45:
            self._quiet_chunks += 1
            if self._quiet_chunks == 3:
                self.offsets.append(now - 0.2)
        else:
            if self._quiet_chunks >= 3:
                self.onsets.append(now)
            self._quiet_chunks = 0

    async def run(self) -> None:
        heartbeat = asyncio.create_task(self._heartbeat())
        closer = asyncio.create_task(self._close_idle_lines())
        runners = [asyncio.create_task(t.run()) for t in self.tracks]
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
                        self._forward(pcm)
                        if self._stop.is_set():
                            break
                    if not self._is_live_source():
                        self.state = "ended"
                        break
                    raise RuntimeError("la fuente se cortó")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    self.errors += 1
                    self.last_error = str(exc)[:300]
                    self.state = "reconnecting"
                    log.warning("[%s] fuente caída: %s", self.session.id, exc)
                    await self._publish_status()
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                    except asyncio.TimeoutError:
                        pass
                    backoff = min(backoff * 2, 30)
        finally:
            # Se deja terminar lo que las sesiones ya estaban traduciendo.
            for track in self.tracks:
                track.put(None)
            if self.state == "ended":
                await asyncio.sleep(4)
            self.stopping = True
            for task in runners:
                task.cancel()
            await asyncio.gather(*runners, return_exceptions=True)
            closer.cancel()
            heartbeat.cancel()
            if self.state != "ended":
                self.state = "stopped"
            await self._publish_status()

    def _is_live_source(self) -> bool:
        from .audio import is_live

        return is_live(self.session.source) and not self._source_factory

    # -- pistas --------------------------------------------------------------------------------

    def _audio_pos(self) -> float:
        return round(self.audio_seconds, 2)

    async def on_original(self, delta: str, lang_code: str | None) -> None:
        async with self._lock:
            lang = self.source_lang or (lang_code or "und")[:2].lower()
            self.original_chars += len(delta)
            await self.original.add(delta, lang)
            if self.original.current is not None:
                self.previous.append(self.original.current.text)

    async def on_translation(self, target: str, delta: str) -> None:
        async with self._lock:
            await self.builders[target].add(delta, target)

    def on_speech(self, target: str, pcm: bytes, rate: int) -> None:
        # Sólo el hub en el mismo proceso sabe repartir audio; un worker remoto publica texto.
        speech = getattr(self.publisher, "speech", None)
        if speech:
            speech(self.session.id, target, pcm, rate)

    async def _close_idle_lines(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            async with self._lock:
                now = time.time()
                for builder in (self.original, *self.builders.values()):
                    if builder.idle(now):
                        builder.close()
                self._watchdog(now)

    def _watchdog(self, now: float) -> None:
        """Corta y reabre una sesión trabada o atrasada, para que los subtítulos vuelvan a estar en vivo."""
        voice = sum(1 for t in self.voice if t > now - self.stall_s) / (self.stall_s * 10)
        voice_start = sum(1 for t in self.voice if t > now - self.startup_s) / (self.startup_s * 10)
        original_flowing = self.original.last_at and now - self.original.last_at < 3
        for track in self.tracks:
            if not track.connected or track.refresh or now - track.last_cut_at < 20:
                continue
            age = now - track.connected_at
            reason = ""
            builder = self.builders[track.target]
            # Una sesión que abre y no devuelve nada: pasó en 2 de 4 arranques en las pruebas. Con voz de
            # entrada, la primera frase llega a los ~3 s; a los 6 s sin nada, se reabre.
            if age > self.startup_s and track.primary and track.last_in_at < track.connected_at and voice_start > 0.5:
                reason = f"abrió hace {age:.0f} s y no devolvió nada con voz de entrada"
            elif age > self.startup_s and not track.primary and track.last_out_at < track.connected_at and original_flowing:
                reason = f"abrió hace {age:.0f} s y no tradujo nada mientras el original avanza"
            if age < self.stall_s + 2 and not reason:
                continue
            if reason:
                pass
            elif track.primary and voice > 0.5 and now - max(track.last_in_at, track.connected_at) > self.stall_s:
                reason = f"hay voz y no llega el original hace {self.stall_s:.0f} s"
            elif (original_flowing and now - max(track.last_out_at, track.connected_at) > self.stall_s
                  and self.original_chars - track.chars_at_out > self.stall_chars):
                # Una oración larga puede demorar la traducción; dos líneas de original sin traducir, no.
                reason = f"el original avanzó {self.original_chars - track.chars_at_out} caracteres sin traducción"
            elif builder.last_lag_ms > self.max_lag_ms and now - builder.last_lag_at < 5:
                reason = f"la traducción llegó {builder.last_lag_ms / 1000:.1f} s tarde"
            elif (track.primary and self.original.last_lag_ms > self.max_lag_ms
                  and now - self.original.last_lag_at < 5):
                reason = f"el original llegó {self.original.last_lag_ms / 1000:.1f} s tarde"
            if reason:
                track.fresh = track.refresh = True
                track.last_cut_at = now
                track.lag_cuts += 1
                self.last_error = f"sesión {track.target} cortada y retomada en vivo: {reason}"
                log.warning("[%s/%s] %s: corto y retomo en vivo", self.session.id, track.target, reason)

    def _pause_lag(self, last_at: float) -> int:
        """Demora entre que el orador se calla y que llega la última palabra de esa frase.

        Sólo se mide si hubo una pausa en los 4 s previos y el orador no volvió a hablar antes de
        que llegara el texto (si no, no se sabe a qué palabras corresponde)."""
        pauses = [t for t in self.offsets if last_at - 4 <= t <= last_at]
        if not pauses:
            return 0
        pause = pauses[-1]
        if any(pause < t < last_at - 0.2 for t in self.onsets):
            return 0
        return int((last_at - pause) * 1000)

    async def _publish(self, cap: Caption) -> None:
        assigned = await self.publisher.caption(cap)
        if assigned and assigned != cap.seq:
            cap.seq = assigned

    def set_language(self, language: str) -> None:
        """La agenda cambió el idioma de la sala: las sesiones se reabren con la pista nueva."""
        self.session.language = language
        self.source_lang = language if language not in ("", "auto") else ""
        self.original.track = self.source_lang or "original"
        for track in self.tracks:
            track.refresh = True

    def set_glossary(self, terms: list[str]) -> bool:
        changed = super().set_glossary(terms)
        if changed:
            # El vocabulario se fija al conectar: se reconecta cada sesión retomando el contexto.
            for track in self.tracks:
                track.refresh = True
        return changed

    def status(self) -> dict:
        data = super().status()
        data["live_sessions"] = f"{sum(t.connected for t in self.tracks)}/{sum(t.wanted.is_set() for t in self.tracks)}"
        data["idle_langs"] = [t.target for t in self.tracks if not t.wanted.is_set()]
        data["paused"] = self.paused
        data["saved_audio_s"] = round(self.saved_audio_s, 1)
        data["reconnects"] = sum(t.reconnects for t in self.tracks)
        data["lag_cuts"] = sum(t.lag_cuts for t in self.tracks)
        data["speech_langs"] = [t.target for t in self.tracks] if hasattr(self.publisher, "speech") else []
        return data


def _join(text: str, delta: str) -> str:
    if not text:
        return delta.strip()
    # Los fragmentos suelen traer su propio espacio inicial; si no, se agrega salvo ante puntuación.
    if delta[:1].isspace() or text[-1:].isspace() or delta[:1] in ",.;:?!…)":
        return (text + delta).replace("  ", " ")
    return f"{text} {delta}"
