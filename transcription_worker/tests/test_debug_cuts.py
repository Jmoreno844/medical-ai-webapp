from __future__ import annotations

import numpy as np

from app.debug_cuts import (
    RETAINED_AUDIO_PADDING_MS,
    RETAINED_SEGMENT_JOIN_SILENCE_MS,
    _build_retained_intervals,
    _trim_samples,
)
from app.vad import VadInterval


def test_build_retained_intervals_adds_padding() -> None:
    retained = _build_retained_intervals(
        [VadInterval(start_ms=2000, end_ms=6000)],
        10000,
    )

    assert retained == [
        VadInterval(start_ms=0, end_ms=2000 + RETAINED_AUDIO_PADDING_MS),
        VadInterval(start_ms=6000 - RETAINED_AUDIO_PADDING_MS, end_ms=10000),
    ]


def test_build_retained_intervals_merges_overlap_after_padding() -> None:
    retained = _build_retained_intervals(
        [VadInterval(start_ms=1000, end_ms=1500)],
        3000,
    )

    assert retained == [VadInterval(start_ms=0, end_ms=3000)]


def test_trim_samples_inserts_silence_between_segments() -> None:
    samples = np.ones(32000, dtype=np.float32)
    trimmed = _trim_samples(
        samples,
        [
            VadInterval(start_ms=0, end_ms=500),
            VadInterval(start_ms=1500, end_ms=2000),
        ],
    )

    expected_speech_samples = 16000
    expected_gap_samples = RETAINED_SEGMENT_JOIN_SILENCE_MS * 16

    assert len(trimmed) == expected_speech_samples + expected_gap_samples
    assert np.allclose(trimmed[8000 : 8000 + expected_gap_samples], 0.0)
