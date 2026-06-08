import { SEGMENTATION_CONFIG } from "./segmentationConfig";
import {
  appendSpeechFrame,
  detectRemovableSilences,
  mergeSpeechIntervals,
} from "./speechIntervals";
import type {
  CutReason,
  SectionCutSignal,
  SegmentState,
  SegmenterSnapshot,
  SpeechInterval,
} from "./types";
import type { VadFrame } from "../vad/VadAdapter";

export type SectionCutListener = (signal: SectionCutSignal) => void;

export class SpeechSegmenter {
  private state: SegmentState = "initializing";
  private wallClockDurationMs = 0;
  private speechDurationMs = 0;
  private currentSilenceMs = 0;
  private lastProcessedTimestampMs = -1;
  private sectionStartTimestampMs: number | null = null;
  private sequence = 0;
  private vadAvailable = true;
  private isPaused = false;
  private speechIntervals: SpeechInterval[] = [];
  private pendingCutReason: CutReason | null = null;
  private listeners: SectionCutListener[] = [];

  onSectionCut(listener: SectionCutListener): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((item) => item !== listener);
    };
  }

  start(vadAvailable: boolean): void {
    this.resetInternal();
    this.vadAvailable = vadAvailable;
    this.state = vadAvailable ? "collecting" : "fallback";
  }

  enterFallback(): void {
    if (this.state === "stopped") {
      return;
    }
    this.state = "fallback";
    this.vadAvailable = false;
  }

  setPaused(paused: boolean): void {
    this.isPaused = paused;
  }

  stop(): SectionCutSignal | null {
    if (this.state === "stopped") {
      return null;
    }

    this.state = "stopped";
    if (this.speechDurationMs > 0) {
      return this.buildCutSignal("manual_stop", false, 0);
    }
    return null;
  }

  processFrame(frame: VadFrame): SectionCutSignal | null {
    if (this.state === "stopped" || this.state === "initializing" || this.isPaused) {
      return null;
    }

    if (frame.timestampMs <= this.lastProcessedTimestampMs) {
      return null;
    }
    this.lastProcessedTimestampMs = frame.timestampMs;
    if (this.sectionStartTimestampMs === null) {
      this.sectionStartTimestampMs = frame.timestampMs;
    }

    this.wallClockDurationMs += frame.durationMs;

    if (frame.isSpeech) {
      this.speechDurationMs += frame.durationMs;
      this.currentSilenceMs = 0;
      const frameStartMs = Math.max(
        0,
        frame.timestampMs - this.sectionStartTimestampMs,
      );
      const frameEndMs = Math.max(
        frameStartMs,
        frame.timestampMs + frame.durationMs - this.sectionStartTimestampMs,
      );
      this.speechIntervals = appendSpeechFrame(
        this.speechIntervals,
        frameStartMs,
        frameEndMs,
      );
    } else {
      this.currentSilenceMs += frame.durationMs;
    }

    this.updateState();

    if (this.pendingCutReason) {
      const reason = this.pendingCutReason;
      this.pendingCutReason = null;
      const forcedCut = reason === "forced_maximum";
      const overlap = forcedCut ? SEGMENTATION_CONFIG.forcedCutOverlapMs : 0;
      return this.emitCut(reason, forcedCut, overlap);
    }

    return null;
  }

  requestManualCut(): SectionCutSignal | null {
    if (this.state === "stopped" || this.speechDurationMs <= 0) {
      return null;
    }
    return this.emitCut("manual_stop", false, 0);
  }

  getSnapshot(): SegmenterSnapshot {
    return {
      state: this.state,
      wallClockDurationMs: this.wallClockDurationMs,
      speechDurationMs: this.speechDurationMs,
      currentSilenceMs: this.currentSilenceMs,
      sequence: this.sequence,
      vadAvailable: this.vadAvailable,
    };
  }

  buildSnapshotCutSignal(
    cutReason: CutReason,
    forcedCut: boolean,
    overlapBeforeMs: number,
  ): SectionCutSignal | null {
    if (this.wallClockDurationMs <= 0 || this.speechDurationMs <= 0) {
      return null;
    }
    return this.buildCutSignal(cutReason, forcedCut, overlapBeforeMs);
  }

  private resetInternal(): void {
    this.state = "initializing";
    this.wallClockDurationMs = 0;
    this.speechDurationMs = 0;
    this.currentSilenceMs = 0;
    this.lastProcessedTimestampMs = -1;
    this.sectionStartTimestampMs = null;
    this.sequence = 0;
    this.speechIntervals = [];
    this.pendingCutReason = null;
    this.isPaused = false;
  }

  private updateState(): void {
    if (this.state === "fallback") {
      this.evaluateFallbackCut();
      return;
    }

    if (this.wallClockDurationMs >= SEGMENTATION_CONFIG.maxWallClockDurationMs) {
      this.pendingCutReason = "wall_clock_limit";
      this.state = "finalizing";
      return;
    }

    if (this.speechDurationMs >= SEGMENTATION_CONFIG.maxSpeechDurationMs) {
      this.pendingCutReason = "forced_maximum";
      this.state = "finalizing";
      return;
    }

    if (this.speechDurationMs >= SEGMENTATION_CONFIG.closingSoonAtSpeechMs) {
      this.state = "closingSoon";
      if (this.currentSilenceMs >= SEGMENTATION_CONFIG.closingSoonSilenceMs) {
        this.pendingCutReason = "closing_soon_silence";
        this.state = "finalizing";
      }
      return;
    }

    if (this.speechDurationMs >= SEGMENTATION_CONFIG.minSpeechDurationMs) {
      this.state = "eligibleForCut";
      if (this.currentSilenceMs >= SEGMENTATION_CONFIG.cutSilenceDurationMs) {
        this.pendingCutReason = "silence_after_minimum";
        this.state = "finalizing";
      }
      return;
    }

    this.state = "collecting";
  }

  private evaluateFallbackCut(): void {
    if (this.wallClockDurationMs >= SEGMENTATION_CONFIG.fallbackSectionMs) {
      this.pendingCutReason = "fallback";
      this.state = "finalizing";
    }
  }

  private buildCutSignal(
    cutReason: CutReason,
    forcedCut: boolean,
    overlapBeforeMs: number,
  ): SectionCutSignal {
    const mergedIntervals = mergeSpeechIntervals(this.speechIntervals)
      .map((interval) => ({
        startMs: Math.max(0, Math.min(interval.startMs, this.wallClockDurationMs)),
        endMs: Math.max(0, Math.min(interval.endMs, this.wallClockDurationMs)),
      }))
      .filter((interval) => interval.endMs > interval.startMs);
    const removableSilences = detectRemovableSilences(
      mergedIntervals,
      this.wallClockDurationMs,
    );

    return {
      cutReason,
      forcedCut,
      overlapBeforeMs,
      wallClockDurationMs: this.wallClockDurationMs,
      speechDurationMs: this.speechDurationMs,
      speechIntervals: mergedIntervals,
      removableSilences,
    };
  }

  private emitCut(
    cutReason: CutReason,
    forcedCut: boolean,
    overlapBeforeMs: number,
  ): SectionCutSignal {
    const signal = this.buildCutSignal(cutReason, forcedCut, overlapBeforeMs);
    this.listeners.forEach((listener) => listener(signal));
    this.sequence += 1;
    this.resetSectionCounters(overlapBeforeMs > 0);
    return signal;
  }

  private resetSectionCounters(keepOverlapContext: boolean): void {
    this.wallClockDurationMs = 0;
    this.speechDurationMs = 0;
    this.currentSilenceMs = 0;
    this.speechIntervals = [];
    this.pendingCutReason = null;
    this.lastProcessedTimestampMs = -1;
    this.sectionStartTimestampMs = null;
    this.state = this.vadAvailable ? "collecting" : "fallback";

    if (keepOverlapContext) {
      // Overlap audio is handled by the recorder; segmenter starts fresh.
    }
  }
}
