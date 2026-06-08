from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import onnxruntime as ort

from app.settings import Settings


@dataclass(frozen=True)
class VadResult:
    is_speech: bool
    speech_ms: int
    speech_ratio: float
    error_code: str | None = None


@dataclass(frozen=True)
class VadInterval:
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class VadAnalysis:
    is_speech: bool
    speech_ms: int
    speech_ratio: float
    speech_intervals: list[VadInterval]
    error_code: str | None = None


@lru_cache(maxsize=1)
def _load_session(model_path: str, intra_op_threads: int) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.intra_op_num_threads = intra_op_threads
    options.inter_op_num_threads = 1
    return ort.InferenceSession(
        model_path,
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


def run_silero_vad(samples: np.ndarray, settings: Settings) -> VadResult:
    analysis = analyze_silero_vad(samples, settings)
    return VadResult(
        is_speech=analysis.is_speech,
        speech_ms=analysis.speech_ms,
        speech_ratio=analysis.speech_ratio,
        error_code=analysis.error_code,
    )


def analyze_silero_vad(samples: np.ndarray, settings: Settings) -> VadAnalysis:
    if samples.size == 0:
        return VadAnalysis(
            is_speech=False,
            speech_ms=0,
            speech_ratio=0.0,
            speech_intervals=[],
        )

    session = _load_session(
        str(settings.silero_model_path),
        settings.ort_intra_op_num_threads,
    )
    state = np.zeros((2, 1, 128), dtype=np.float32)
    sample_rate = np.array(16000, dtype=np.int64)

    window_size = 512
    speech_frames = 0
    total_frames = 0
    speech_intervals: list[VadInterval] = []
    current_interval_start_ms: int | None = None

    for offset in range(0, len(samples), window_size):
        chunk = samples[offset : offset + window_size]
        if len(chunk) < window_size:
            chunk = np.pad(chunk, (0, window_size - len(chunk)))
        output, state = session.run(
            None,
            {
                "input": chunk.reshape(1, -1).astype(np.float32),
                "state": state,
                "sr": sample_rate,
            },
        )
        total_frames += 1
        frame_start_ms = int(offset / 16000 * 1000)
        is_speech_frame = float(np.asarray(output).reshape(-1)[0]) >= settings.vad_threshold
        if is_speech_frame:
            speech_frames += 1
            if current_interval_start_ms is None:
                current_interval_start_ms = frame_start_ms
        elif current_interval_start_ms is not None:
            speech_intervals.append(
                VadInterval(
                    start_ms=current_interval_start_ms,
                    end_ms=frame_start_ms,
                )
            )
            current_interval_start_ms = None

    frame_ms = int(window_size / 16000 * 1000)
    if current_interval_start_ms is not None:
        speech_intervals.append(
            VadInterval(
                start_ms=current_interval_start_ms,
                end_ms=total_frames * frame_ms,
            )
        )
    speech_intervals = _merge_intervals(speech_intervals)
    speech_ms = speech_frames * frame_ms
    speech_ratio = speech_frames / total_frames if total_frames else 0.0
    is_speech = (
        speech_ms >= settings.vad_min_speech_ms
        and speech_ratio >= settings.vad_min_speech_ratio
    )
    return VadAnalysis(
        is_speech=is_speech,
        speech_ms=speech_ms,
        speech_ratio=speech_ratio,
        speech_intervals=speech_intervals,
    )


def _merge_intervals(
    intervals: list[VadInterval],
    max_gap_ms: int = 300,
) -> list[VadInterval]:
    if not intervals:
        return []

    merged: list[VadInterval] = [intervals[0]]
    for current in intervals[1:]:
        last = merged[-1]
        if current.start_ms - last.end_ms <= max_gap_ms:
            merged[-1] = VadInterval(
                start_ms=last.start_ms,
                end_ms=max(last.end_ms, current.end_ms),
            )
            continue
        merged.append(current)
    return merged
