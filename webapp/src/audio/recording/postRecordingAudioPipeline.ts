import { getBestSupportedAudioType } from "@/features/encuentroHeader/hooks/audio/utils";
import { encodeMono16kToOpusBlob } from "./offlineOpusEncoder";
import {
  buildRetainedIntervals,
  detectRemovableSilences,
  mergeSpeechIntervals,
} from "../segmentation/speechIntervals";
import type {
  AudioSectionMetadata,
  CutReason,
  RemovableSilence,
  SpeechInterval,
} from "../segmentation/types";

type BrowserAudioContextCtor = typeof AudioContext & {
  new (options?: AudioContextOptions): AudioContext;
};

export type PreparedSectionArtifacts = {
  originalBlob: Blob;
  originalMimeType: string;
  clippedBlob: Blob;
  clippedMimeType: string;
  normalizedMetadata: AudioSectionMetadata;
  retainedIntervals: SpeechInterval[];
  processingTimingsMs: FrontendAudioProcessingTimings;
};

export type FrontendAudioProcessingTimings = {
  decodeMs: number;
  normalizeAndCutMs: number;
  encodeMs: number;
  totalMs: number;
  encoderBackend: "webcodecs" | "opus-recorder";
  encoderFallbackReason: string | null;
};

export type FrontendCutMetadataLike = {
  sectionDurationMs: number;
  speechDurationMs: number;
  speechIntervals: SpeechInterval[];
  removableSilences: RemovableSilence[];
  overlapMs: number;
  cutReason: string;
};

const TARGET_SAMPLE_RATE = 16_000;
export const RETAINED_SEGMENT_JOIN_SILENCE_MS = 1_000;

const getAudioContextCtor = (): BrowserAudioContextCtor => {
  const ctor = (window.AudioContext ??
    (window as Window & { webkitAudioContext?: BrowserAudioContextCtor })
      .webkitAudioContext) as BrowserAudioContextCtor | undefined;
  if (!ctor) {
    throw new Error("AudioContext not supported");
  }
  return ctor;
};

const mixToMono = (audioBuffer: AudioBuffer): Float32Array => {
  if (audioBuffer.numberOfChannels === 1) {
    return audioBuffer.getChannelData(0).slice();
  }

  const mono = new Float32Array(audioBuffer.length);
  for (
    let channelIndex = 0;
    channelIndex < audioBuffer.numberOfChannels;
    channelIndex += 1
  ) {
    const channel = audioBuffer.getChannelData(channelIndex);
    for (let sampleIndex = 0; sampleIndex < channel.length; sampleIndex += 1) {
      mono[sampleIndex] += channel[sampleIndex] / audioBuffer.numberOfChannels;
    }
  }
  return mono;
};

export const trimMonoSamples = (
  samples: Float32Array,
  retainedIntervals: SpeechInterval[],
): Float32Array => {
  const segments: Float32Array[] = [];
  for (const interval of retainedIntervals) {
    const startSample = Math.max(
      0,
      Math.min(samples.length, Math.round((interval.startMs / 1000) * TARGET_SAMPLE_RATE)),
    );
    const endSample = Math.max(
      startSample,
      Math.min(samples.length, Math.round((interval.endMs / 1000) * TARGET_SAMPLE_RATE)),
    );
    if (endSample > startSample) {
      segments.push(samples.slice(startSample, endSample));
    }
  }

  if (segments.length === 0) {
    return samples;
  }
  if (segments.length === 1) {
    return segments[0];
  }

  const gapLength = Math.round(
    (RETAINED_SEGMENT_JOIN_SILENCE_MS / 1000) * TARGET_SAMPLE_RATE,
  );
  const totalLength =
    segments.reduce((sum, segment) => sum + segment.length, 0) +
    gapLength * (segments.length - 1);
  const merged = new Float32Array(totalLength);
  let offset = 0;
  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index];
    merged.set(segment, offset);
    offset += segment.length;
    if (index < segments.length - 1) {
      offset += gapLength;
    }
  }
  return merged;
};

const decodeToMono16k = async (
  blob: Blob,
): Promise<{ samples: Float32Array; durationMs: number }> => {
  const AudioContextCtor = getAudioContextCtor();
  const audioContext = new AudioContextCtor({ sampleRate: TARGET_SAMPLE_RATE });
  try {
    const buffer = await audioContext.decodeAudioData(await blob.arrayBuffer());
    return {
      samples: mixToMono(buffer),
      durationMs: Math.round(buffer.duration * 1000),
    };
  } finally {
    void audioContext.close().catch(() => undefined);
  }
};

export const prepareRecordedSectionArtifacts = async (
  originalBlob: Blob,
  metadata: AudioSectionMetadata,
): Promise<PreparedSectionArtifacts> => {
  const startedAt = performance.now();
  const decodeStartedAt = performance.now();
  const { samples, durationMs } = await decodeToMono16k(originalBlob);
  const decodeMs = performance.now() - decodeStartedAt;
  const normalizeStartedAt = performance.now();
  const normalizedDurationMs = Math.max(durationMs, metadata.wallClockDurationMs);
  const normalizedSpeechIntervals = mergeSpeechIntervals(metadata.speechIntervals)
    .map((interval) => ({
      startMs: Math.max(0, Math.min(Math.round(interval.startMs), normalizedDurationMs)),
      endMs: Math.max(0, Math.min(Math.round(interval.endMs), normalizedDurationMs)),
    }))
    .filter((interval) => interval.endMs > interval.startMs);
  const normalizedRemovableSilences = detectRemovableSilences(
    normalizedSpeechIntervals,
    normalizedDurationMs,
  ).map((interval) => ({
    startMs: Math.round(interval.startMs),
    endMs: Math.round(interval.endMs),
  }));
  const retainedIntervals = buildRetainedIntervals(
    normalizedRemovableSilences,
    normalizedDurationMs,
  );
  const clippedSamples = trimMonoSamples(samples, retainedIntervals);
  const normalizeAndCutMs = performance.now() - normalizeStartedAt;
  const encodeStartedAt = performance.now();
  const clippedEncoding = await encodeMono16kToOpusBlob(clippedSamples);
  const encodeMs = performance.now() - encodeStartedAt;
  const totalMs = performance.now() - startedAt;
  const clippedBlob = clippedEncoding.blob;

  return {
    originalBlob,
    originalMimeType: originalBlob.type || getBestSupportedAudioType(),
    clippedBlob,
    clippedMimeType: clippedBlob.type || "audio/ogg;codecs=opus",
    normalizedMetadata: {
      ...metadata,
      wallClockDurationMs: normalizedDurationMs,
      speechIntervals: normalizedSpeechIntervals,
      removableSilences: normalizedRemovableSilences,
    },
    retainedIntervals,
    processingTimingsMs: {
      decodeMs: Math.round(decodeMs),
      normalizeAndCutMs: Math.round(normalizeAndCutMs),
      encodeMs: Math.round(encodeMs),
      totalMs: Math.round(totalMs),
      encoderBackend: clippedEncoding.encoderBackend,
      encoderFallbackReason: clippedEncoding.fallbackReason,
    },
  };
};

const toCutReason = (value: string): CutReason => {
  switch (value) {
    case "silence_after_minimum":
    case "closing_soon_silence":
    case "forced_maximum":
    case "wall_clock_limit":
    case "manual_stop":
    case "fallback":
      return value;
    default:
      return "manual_stop";
  }
};

export const buildAudioSectionMetadataFromFrontendCut = ({
  sectionId,
  sequence,
  audioMimeType,
  vadAvailable = true,
  vadModelVersion = "silero_frontend",
  cut,
}: {
  sectionId: string;
  sequence: number;
  audioMimeType: string;
  vadAvailable?: boolean;
  vadModelVersion?: string;
  cut: FrontendCutMetadataLike;
}): AudioSectionMetadata => ({
  sectionId,
  sequence,
  wallClockDurationMs: Math.max(0, Math.round(cut.sectionDurationMs)),
  speechDurationMs: Math.max(0, Math.round(cut.speechDurationMs)),
  speechIntervals: cut.speechIntervals,
  removableSilences: cut.removableSilences,
  cutReason: toCutReason(cut.cutReason),
  forcedCut:
    cut.cutReason === "forced_maximum" || cut.cutReason === "wall_clock_limit",
  overlapBeforeMs: Math.max(0, Math.round(cut.overlapMs)),
  vadAvailable,
  vadModelVersion,
  audioMimeType,
});
