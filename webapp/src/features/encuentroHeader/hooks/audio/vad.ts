export const AUDIO_SEGMENTATION_CONFIG = {
  preRollMs: 400,
  tailMs: 600,
  midSectionSilenceMs: 500,
  midSectionThresholdMs: 20000,
  endSectionSilenceMs: 350,
  endSectionThresholdMs: 25000,
  minSectionMs: 1000,
  minSpeechFramesPerSection: 4,
  maxSectionMs: 33000,
  forcedOverlapMs: 400,
  fallbackSectionMs: 20000,
  vadPollIntervalMs: 120,
  vadRmsThreshold: 0.018,
  vadPeakThreshold: 0.05,
} as const;

export const VAD_ANALYSER_FFT_SIZE = 2048;

export type VoiceActivitySample = {
  isSpeech: boolean;
  rms: number;
  peak: number;
};

export type NaturalPauseDecision = {
  nowMs: number;
  sectionStartedAtMs: number;
  lastSpeechAtMs: number;
  hasDetectedSpeech: boolean;
};

export type SectionVoiceDecision = {
  hasDetectedSpeech: boolean;
  speechFrameCount: number;
  sectionDurationMs: number;
};

export const getNaturalPauseThresholdMs = (
  sectionDurationMs: number,
): number => {
  if (sectionDurationMs >= AUDIO_SEGMENTATION_CONFIG.endSectionThresholdMs) {
    return AUDIO_SEGMENTATION_CONFIG.endSectionSilenceMs;
  }

  if (sectionDurationMs >= AUDIO_SEGMENTATION_CONFIG.midSectionThresholdMs) {
    return AUDIO_SEGMENTATION_CONFIG.midSectionSilenceMs;
  }

  return AUDIO_SEGMENTATION_CONFIG.preRollMs + AUDIO_SEGMENTATION_CONFIG.tailMs;
};

export const detectVoiceActivity = (
  timeDomainData: Float32Array,
): VoiceActivitySample => {
  let sumSquares = 0;
  let peak = 0;

  for (const sample of timeDomainData) {
    const absoluteValue = Math.abs(sample);
    sumSquares += sample * sample;
    if (absoluteValue > peak) {
      peak = absoluteValue;
    }
  }

  const rms = Math.sqrt(sumSquares / timeDomainData.length);
  const isSpeech =
    rms >= AUDIO_SEGMENTATION_CONFIG.vadRmsThreshold ||
    peak >= AUDIO_SEGMENTATION_CONFIG.vadPeakThreshold;

  return {
    isSpeech,
    rms,
    peak,
  };
};

export const shouldFlushOnNaturalPause = ({
  nowMs,
  sectionStartedAtMs,
  lastSpeechAtMs,
  hasDetectedSpeech,
}: NaturalPauseDecision): boolean => {
  if (!hasDetectedSpeech) {
    return false;
  }

  const sectionDurationMs = nowMs - sectionStartedAtMs;
  if (sectionDurationMs < AUDIO_SEGMENTATION_CONFIG.minSectionMs) {
    return false;
  }

  const stableSilenceMs = nowMs - lastSpeechAtMs;
  const naturalPauseThresholdMs = getNaturalPauseThresholdMs(sectionDurationMs);
  return stableSilenceMs >= naturalPauseThresholdMs;
};

export const shouldForceSectionCut = (sectionDurationMs: number): boolean => {
  return sectionDurationMs >= AUDIO_SEGMENTATION_CONFIG.maxSectionMs;
};

export const shouldUploadSectionForTranscription = ({
  hasDetectedSpeech,
  speechFrameCount,
  sectionDurationMs,
}: SectionVoiceDecision): boolean => {
  if (!hasDetectedSpeech) {
    return false;
  }

  if (sectionDurationMs < AUDIO_SEGMENTATION_CONFIG.minSectionMs) {
    return false;
  }

  return (
    speechFrameCount >= AUDIO_SEGMENTATION_CONFIG.minSpeechFramesPerSection
  );
};
