export type SegmentState =
  | "initializing"
  | "collecting"
  | "eligibleForCut"
  | "closingSoon"
  | "finalizing"
  | "fallback"
  | "stopped";

export type CutReason =
  | "silence_after_minimum"
  | "closing_soon_silence"
  | "forced_maximum"
  | "wall_clock_limit"
  | "manual_stop"
  | "fallback";

export interface SpeechInterval {
  startMs: number;
  endMs: number;
}

export interface RemovableSilence {
  startMs: number;
  endMs: number;
}

export interface AudioSectionMetadata {
  sectionId: string;
  sequence: number;

  wallClockDurationMs: number;
  speechDurationMs: number;

  speechIntervals: SpeechInterval[];
  removableSilences: RemovableSilence[];

  cutReason: CutReason;
  forcedCut: boolean;
  overlapBeforeMs: number;

  vadAvailable: boolean;
  vadModelVersion?: string;
  audioMimeType: string;
}

export interface SectionCutSignal {
  cutReason: CutReason;
  forcedCut: boolean;
  overlapBeforeMs: number;
  wallClockDurationMs: number;
  speechDurationMs: number;
  speechIntervals: SpeechInterval[];
  removableSilences: RemovableSilence[];
}

export interface SegmenterSnapshot {
  state: SegmentState;
  wallClockDurationMs: number;
  speechDurationMs: number;
  currentSilenceMs: number;
  sequence: number;
  vadAvailable: boolean;
}
