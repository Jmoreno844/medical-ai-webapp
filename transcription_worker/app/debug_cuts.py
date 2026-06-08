from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.audio import encode_float32_pcm_to_wav
from app.settings import Settings
from app.vad import VadAnalysis, VadInterval, analyze_silero_vad

REMOVABLE_SILENCE_MS = 3000
RETAINED_AUDIO_PADDING_MS = 300
RETAINED_SEGMENT_JOIN_SILENCE_MS = 1000


@dataclass(frozen=True)
class DebugCutMetadata:
    original_duration_ms: int
    retained_duration_ms: int
    speech_duration_ms: int
    speech_ratio: float
    retained_intervals: list[VadInterval]
    removable_silences: list[VadInterval]
    speech_intervals: list[VadInterval]
    trim_applied: bool


def build_worker_debug_cut(
    samples: np.ndarray,
    settings: Settings,
) -> tuple[VadAnalysis, DebugCutMetadata, bytes]:
    analysis = analyze_silero_vad(samples, settings)
    original_duration_ms = _samples_to_ms(len(samples))
    removable_silences = _detect_removable_silences(
        analysis.speech_intervals,
        original_duration_ms,
    )
    retained_intervals = _build_retained_intervals(
        removable_silences,
        original_duration_ms,
    )
    retained_duration_ms = sum(
        interval.end_ms - interval.start_ms for interval in retained_intervals
    )
    trimmed_samples = _trim_samples(samples, retained_intervals)
    trimmed_audio_bytes = encode_float32_pcm_to_wav(trimmed_samples)

    return (
        analysis,
        DebugCutMetadata(
            original_duration_ms=original_duration_ms,
            retained_duration_ms=retained_duration_ms,
            speech_duration_ms=analysis.speech_ms,
            speech_ratio=analysis.speech_ratio,
            retained_intervals=retained_intervals,
            removable_silences=removable_silences,
            speech_intervals=analysis.speech_intervals,
            trim_applied=bool(removable_silences),
        ),
        trimmed_audio_bytes,
    )


def _detect_removable_silences(
    speech_intervals: list[VadInterval],
    total_duration_ms: int,
) -> list[VadInterval]:
    if not speech_intervals:
        return []

    removable: list[VadInterval] = []

    leading_end = speech_intervals[0].start_ms
    if leading_end >= REMOVABLE_SILENCE_MS:
        removable.append(VadInterval(start_ms=0, end_ms=leading_end))

    for index in range(len(speech_intervals) - 1):
        gap_start = speech_intervals[index].end_ms
        gap_end = speech_intervals[index + 1].start_ms
        if gap_end - gap_start >= REMOVABLE_SILENCE_MS:
            removable.append(VadInterval(start_ms=gap_start, end_ms=gap_end))

    trailing_start = speech_intervals[-1].end_ms
    if total_duration_ms - trailing_start >= REMOVABLE_SILENCE_MS:
        removable.append(VadInterval(start_ms=trailing_start, end_ms=total_duration_ms))

    return removable


def _build_retained_intervals(
    removable_silences: list[VadInterval],
    total_duration_ms: int,
) -> list[VadInterval]:
    base_intervals: list[VadInterval] = []
    if not removable_silences:
        base_intervals.append(VadInterval(start_ms=0, end_ms=total_duration_ms))
    else:
        cursor = 0
        for silence in removable_silences:
            if silence.start_ms > cursor:
                base_intervals.append(
                    VadInterval(start_ms=cursor, end_ms=silence.start_ms)
                )
            cursor = silence.end_ms
        if cursor < total_duration_ms:
            base_intervals.append(
                VadInterval(start_ms=cursor, end_ms=total_duration_ms)
            )

    padded_intervals = [
        VadInterval(
            start_ms=max(0, interval.start_ms - RETAINED_AUDIO_PADDING_MS),
            end_ms=min(total_duration_ms, interval.end_ms + RETAINED_AUDIO_PADDING_MS),
        )
        for interval in base_intervals
    ]
    if not padded_intervals:
        return []

    merged: list[VadInterval] = [padded_intervals[0]]
    for current in padded_intervals[1:]:
        last = merged[-1]
        if current.start_ms <= last.end_ms:
            merged[-1] = VadInterval(
                start_ms=last.start_ms,
                end_ms=max(last.end_ms, current.end_ms),
            )
        else:
            merged.append(current)
    return merged


def _trim_samples(samples: np.ndarray, retained_intervals: list[VadInterval]) -> np.ndarray:
    segments: list[np.ndarray] = []
    for interval in retained_intervals:
        start_sample = _ms_to_sample_index(interval.start_ms)
        end_sample = _ms_to_sample_index(interval.end_ms)
        if end_sample > start_sample:
            segments.append(samples[start_sample:end_sample])

    if not segments:
        return samples
    if len(segments) == 1:
        return segments[0]

    gap_samples = np.zeros(_ms_to_sample_index(RETAINED_SEGMENT_JOIN_SILENCE_MS), dtype=np.float32)
    stitched: list[np.ndarray] = []
    for index, segment in enumerate(segments):
        stitched.append(segment)
        if index < len(segments) - 1:
            stitched.append(gap_samples)
    return np.concatenate(stitched)


def _ms_to_sample_index(value_ms: int) -> int:
    return int(value_ms * 16)


def _samples_to_ms(sample_count: int) -> int:
    return int(sample_count / 16)
