import { SEGMENTATION_CONFIG } from "./segmentationConfig";
import type { RemovableSilence, SpeechInterval } from "./types";

export const RETAINED_AUDIO_PADDING_MS = 300;

export function mergeSpeechIntervals(
  intervals: SpeechInterval[],
  maxGapMs = 300,
): SpeechInterval[] {
  if (intervals.length === 0) {
    return [];
  }

  const sorted = [...intervals].sort((a, b) => a.startMs - b.startMs);
  const merged: SpeechInterval[] = [{ ...sorted[0] }];

  for (let index = 1; index < sorted.length; index += 1) {
    const current = sorted[index];
    const last = merged[merged.length - 1];
    if (current.startMs - last.endMs <= maxGapMs) {
      last.endMs = Math.max(last.endMs, current.endMs);
    } else {
      merged.push({ ...current });
    }
  }

  return merged;
}

export function detectRemovableSilences(
  speechIntervals: SpeechInterval[],
  wallClockDurationMs: number,
): RemovableSilence[] {
  const merged = mergeSpeechIntervals(speechIntervals);
  const removable: RemovableSilence[] = [];

  if (merged.length === 0) {
    return removable;
  }

  const firstGapStart = 0;
  const firstGapEnd = merged[0].startMs;
  if (firstGapEnd - firstGapStart >= SEGMENTATION_CONFIG.removableSilenceDurationMs) {
    removable.push({ startMs: firstGapStart, endMs: firstGapEnd });
  }

  for (let index = 0; index < merged.length - 1; index += 1) {
    const gapStart = merged[index].endMs;
    const gapEnd = merged[index + 1].startMs;
    const gapDuration = gapEnd - gapStart;
    if (gapDuration >= SEGMENTATION_CONFIG.removableSilenceDurationMs) {
      removable.push({ startMs: gapStart, endMs: gapEnd });
    }
  }

  const lastInterval = merged[merged.length - 1];
  const trailingStart = lastInterval.endMs;
  const trailingEnd = wallClockDurationMs;
  if (trailingEnd - trailingStart >= SEGMENTATION_CONFIG.removableSilenceDurationMs) {
    removable.push({ startMs: trailingStart, endMs: trailingEnd });
  }

  return removable;
}

export function buildRetainedIntervals(
  removableSilences: RemovableSilence[],
  totalDurationMs: number,
  paddingMs = RETAINED_AUDIO_PADDING_MS,
): SpeechInterval[] {
  const baseIntervals: SpeechInterval[] = [];
  if (removableSilences.length === 0) {
    baseIntervals.push({ startMs: 0, endMs: totalDurationMs });
  } else {
    let cursor = 0;
    for (const silence of removableSilences) {
      if (silence.startMs > cursor) {
        baseIntervals.push({ startMs: cursor, endMs: silence.startMs });
      }
      cursor = silence.endMs;
    }
    if (cursor < totalDurationMs) {
      baseIntervals.push({ startMs: cursor, endMs: totalDurationMs });
    }
  }

  if (paddingMs <= 0) {
    return baseIntervals;
  }

  const padded = baseIntervals.map((interval) => ({
    startMs: Math.max(0, interval.startMs - paddingMs),
    endMs: Math.min(totalDurationMs, interval.endMs + paddingMs),
  }));

  if (padded.length === 0) {
    return [];
  }

  const merged: SpeechInterval[] = [{ ...padded[0] }];
  for (let index = 1; index < padded.length; index += 1) {
    const current = padded[index];
    const last = merged[merged.length - 1];
    if (current.startMs <= last.endMs) {
      last.endMs = Math.max(last.endMs, current.endMs);
    } else {
      merged.push({ ...current });
    }
  }

  return merged;
}

export function appendSpeechFrame(
  intervals: SpeechInterval[],
  frameStartMs: number,
  frameEndMs: number,
): SpeechInterval[] {
  if (intervals.length === 0) {
    return [{ startMs: frameStartMs, endMs: frameEndMs }];
  }

  const last = intervals[intervals.length - 1];
  if (frameStartMs <= last.endMs + 50) {
    last.endMs = Math.max(last.endMs, frameEndMs);
    return intervals;
  }

  return [...intervals, { startMs: frameStartMs, endMs: frameEndMs }];
}
