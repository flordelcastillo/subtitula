"""Corte del audio en tramos cortos, siguiendo las pausas del orador.

La latencia de un subtítulo es, en lo esencial, el largo del tramo más el tiempo del modelo.
Cortar por silencio (y no cada N segundos fijos) evita partir palabras, que es lo que más
degrada la transcripción, y permite tramos cortos cuando el orador hace pausas.

Trabaja sobre PCM s16le mono a 16 kHz, en frames de 30 ms, sin dependencias fuera de numpy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16_000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
BYTES_PER_SAMPLE = 2


@dataclass
class Segment:
    pcm: bytes
    start: float  # segundos de audio desde que arrancó la sesión
    end: float
    speech_ratio: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class SegmenterConfig:
    min_seconds: float = 1.2
    max_seconds: float = 5.0
    # Pausa que alcanza para cerrar un tramo cuando ya pasó min_seconds.
    silence_ms: int = 300
    # Silencio que se conserva antes del habla, para no comerse el ataque de la primera sílaba.
    preroll_ms: int = 150
    # Un frame es habla si supera el piso de ruido por este margen (dB) y el mínimo absoluto.
    margin_db: float = 9.0
    min_speech_dbfs: float = -50.0
    # Menos de esta fracción de frames con habla: el tramo se descarta (no se paga API por silencio).
    min_speech_ratio: float = 0.12


def frame_dbfs(frame: np.ndarray) -> float:
    if frame.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
    return 20.0 * np.log10(max(rms, 1e-9) / 32768.0)


class Segmenter:
    """Recibe PCM en pedazos de cualquier tamaño y devuelve tramos listos para transcribir."""

    def __init__(self, cfg: SegmenterConfig | None = None):
        self.cfg = cfg or SegmenterConfig()
        self._pending = b""  # bytes que todavía no completan un frame
        self._frames: list[np.ndarray] = []
        self._levels: list[float] = []
        self._speech: list[bool] = []
        self._start_frame = 0  # índice global del primer frame del tramo en curso
        self._total_frames = 0
        self._noise_floor = -60.0

    # -- API pública ---------------------------------------------------------------------------

    def feed(self, pcm: bytes) -> list[Segment]:
        data = self._pending + pcm
        usable = len(data) - len(data) % (FRAME_SAMPLES * BYTES_PER_SAMPLE)
        self._pending = data[usable:]
        out: list[Segment] = []
        if usable == 0:
            return out
        samples = np.frombuffer(data[:usable], dtype=np.int16)
        for frame in samples.reshape(-1, FRAME_SAMPLES):
            seg = self._push_frame(frame)
            if seg is not None:
                out.append(seg)
        return out

    def flush(self) -> list[Segment]:
        seg = self._emit(len(self._frames))
        return [seg] if seg is not None else []

    # -- interno -------------------------------------------------------------------------------

    def _push_frame(self, frame: np.ndarray) -> Segment | None:
        cfg = self.cfg
        level = frame_dbfs(frame)
        is_speech = level > max(self._noise_floor + cfg.margin_db, cfg.min_speech_dbfs)
        # El piso de ruido baja rápido y sube lento: sigue al ruido de sala sin confundirlo con voz.
        if level < self._noise_floor:
            self._noise_floor = 0.7 * self._noise_floor + 0.3 * level
        elif not is_speech:
            self._noise_floor = 0.995 * self._noise_floor + 0.005 * level

        self._frames.append(frame)
        self._levels.append(level)
        self._speech.append(is_speech)
        self._total_frames += 1

        n = len(self._frames)
        frame_s = FRAME_MS / 1000
        duration = n * frame_s

        # Sin habla todavía: sólo se guarda un pre-roll corto.
        if not any(self._speech):
            keep = max(1, cfg.preroll_ms // FRAME_MS)
            if n > keep:
                drop = n - keep
                self._drop_head(drop)
            return None

        silence_frames = max(1, cfg.silence_ms // FRAME_MS)
        trailing_silence = n >= silence_frames and not any(self._speech[-silence_frames:])
        if duration >= cfg.min_seconds and trailing_silence:
            return self._emit(n)
        if duration >= cfg.max_seconds:
            # Corte forzado en el frame más silencioso del último segundo y medio.
            window = min(n - 1, int(1.5 / frame_s))
            tail = np.array(self._levels[n - window:])
            cut = n - window + int(np.argmin(tail)) + 1
            return self._emit(cut)
        return None

    def _drop_head(self, count: int) -> None:
        del self._frames[:count]
        del self._levels[:count]
        del self._speech[:count]
        self._start_frame += count

    def _emit(self, count: int) -> Segment | None:
        if count <= 0 or not self._frames:
            return None
        frames = self._frames[:count]
        speech = self._speech[:count]
        start = self._start_frame * FRAME_MS / 1000
        end = (self._start_frame + count) * FRAME_MS / 1000
        self._drop_head(count)
        ratio = sum(speech) / len(speech)
        if ratio < self.cfg.min_speech_ratio:
            return None
        return Segment(pcm=np.concatenate(frames).tobytes(), start=start, end=end, speech_ratio=ratio)
