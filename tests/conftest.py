import subprocess
from pathlib import Path

import numpy as np
import pytest

from subtitula.segmenter import SAMPLE_RATE


def speechlike(seconds: float, freq: float = 220.0, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    # Tono con modulación silábica (~4 Hz): alcanza para que el detector de energía lo vea como voz.
    env = 0.6 + 0.4 * np.sin(2 * np.pi * 4 * t)
    return (amp * env * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)


def silence(seconds: float, noise: float = 0.002) -> np.ndarray:
    rng = np.random.default_rng(0)
    return (rng.normal(0, noise, int(seconds * SAMPLE_RATE)) * 32767).astype(np.int16)


@pytest.fixture
def talk_wav(tmp_path: Path) -> Path:
    """Audio sintético de ~12 s: frases de 2-3 s separadas por pausas."""
    parts = []
    for dur in (2.5, 3.0, 2.0, 2.5):
        parts += [speechlike(dur), silence(0.6)]
    pcm = np.concatenate([silence(0.5), *parts]).tobytes()
    raw = tmp_path / "talk.raw"
    raw.write_bytes(pcm)
    wav = tmp_path / "talk.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1",
                    "-i", str(raw), str(wav)], check=True)
    return wav
