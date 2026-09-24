import numpy as np

from subtitula.segmenter import SAMPLE_RATE, Segmenter, SegmenterConfig

from .conftest import silence, speechlike


def feed_all(seg: Segmenter, pcm: np.ndarray, chunk: int = 1600):
    raw = pcm.tobytes()
    out = []
    for i in range(0, len(raw), chunk * 2):
        out += seg.feed(raw[i:i + chunk * 2])
    return out + seg.flush()


def test_cuts_on_pauses():
    audio = np.concatenate([silence(0.5), speechlike(2.0), silence(0.6), speechlike(2.5), silence(0.6)])
    segs = feed_all(Segmenter(), audio)
    assert len(segs) == 2
    # El primer tramo empieza cerca del habla (pre-roll corto) y termina en la pausa.
    assert 0.2 <= segs[0].start <= 0.5
    assert 2.4 <= segs[0].end <= 3.2
    assert all(1.2 <= s.duration <= 5.0 for s in segs)


def test_long_speech_is_forced_under_max():
    audio = np.concatenate([speechlike(12.0), silence(0.5)])
    segs = feed_all(Segmenter(SegmenterConfig(max_seconds=4.0)), audio)
    assert len(segs) >= 3
    assert all(s.duration <= 4.0 + 0.05 for s in segs)
    # No se pierde audio: los tramos son contiguos.
    for a, b in zip(segs, segs[1:]):
        assert abs(a.end - b.start) < 1e-6


def test_silence_is_not_sent():
    assert feed_all(Segmenter(), silence(10.0)) == []


def test_odd_chunk_sizes_do_not_lose_samples():
    audio = np.concatenate([speechlike(3.0), silence(0.6)])
    segs = feed_all(Segmenter(), audio, chunk=777)
    total = sum(len(s.pcm) for s in segs) // 2
    assert total >= int(2.9 * SAMPLE_RATE)
