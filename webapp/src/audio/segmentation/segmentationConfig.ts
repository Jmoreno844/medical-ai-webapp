export const SEGMENTATION_CONFIG = {
  minSpeechDurationMs: 20_000,
  maxSpeechDurationMs: 90_000,

  cutSilenceDurationMs: 1_500,
  closingSoonAtSpeechMs: 87_000,
  closingSoonSilenceMs: 500,

  forcedCutOverlapMs: 400,

  removableSilenceDurationMs: 3_000,
  speechPaddingBeforeMs: 200,
  speechPaddingAfterMs: 250,

  maxWallClockDurationMs: 180_000,

  speechThreshold: 0.5,
  negativeSpeechThreshold: 0.35,

  /** Fallback timer segmentation when Silero is unavailable (wall clock). */
  fallbackSectionMs: 90_000,

  vadInitTimeoutMs: 5_000,
  vadModelVersion: "silero_v4",
  vadFrameDurationMs: 32,
  vadSampleRate: 16_000,
  vadWindowSamples: 512,
  vadScriptProcessorBufferSize: 4096,

  /** RMS fallback VAD (energy-based). */
  fallbackVadPollIntervalMs: 120,
  fallbackVadRmsThreshold: 0.018,
  fallbackVadPeakThreshold: 0.05,
  fallbackVadAnalyserFftSize: 2048,
} as const;

export type SegmentationConfig = typeof SEGMENTATION_CONFIG;
