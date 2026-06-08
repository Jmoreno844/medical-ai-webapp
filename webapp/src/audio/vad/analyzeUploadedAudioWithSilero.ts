import { SEGMENTATION_CONFIG } from "../segmentation/segmentationConfig";
import {
  appendSpeechFrame,
  buildRetainedIntervals,
  detectRemovableSilences,
  mergeSpeechIntervals,
} from "../segmentation/speechIntervals";
import type { RemovableSilence, SpeechInterval } from "../segmentation/types";

type BrowserAudioContextCtor = typeof AudioContext & {
  new (options?: AudioContextOptions): AudioContext;
};

type WorkerInbound =
  | { type: "init"; modelUrl: string }
  | { type: "smoke_infer" }
  | {
      type: "pcm_chunk";
      samples: Float32Array;
      timestampMs: number;
      durationMs: number;
    }
  | { type: "destroy" };

type WorkerOutbound =
  | { type: "ready" }
  | { type: "error"; message: string }
  | {
      type: "frame";
      timestampMs: number;
      durationMs: number;
      speechProbability: number;
    };

export type UploadedAudioFrontendAnalysis = {
  sectionDurationMs: number;
  speechDurationMs: number;
  speechFrameCount: number;
  hasDetectedSpeech: boolean;
  speechIntervals: SpeechInterval[];
  removableSilences: RemovableSilence[];
  retainedIntervals: SpeechInterval[];
};

const MODEL_URL = "/vad/silero_vad.onnx";

function getAudioContextCtor(): BrowserAudioContextCtor {
  const ctor = (window.AudioContext ??
    (window as Window & { webkitAudioContext?: BrowserAudioContextCtor })
      .webkitAudioContext) as BrowserAudioContextCtor | undefined;
  if (!ctor) {
    throw new Error("AudioContext not supported");
  }
  return ctor;
}

function mixToMono(audioBuffer: AudioBuffer): Float32Array {
  if (audioBuffer.numberOfChannels === 1) {
    return audioBuffer.getChannelData(0).slice();
  }

  const mono = new Float32Array(audioBuffer.length);
  for (let channelIndex = 0; channelIndex < audioBuffer.numberOfChannels; channelIndex += 1) {
    const channel = audioBuffer.getChannelData(channelIndex);
    for (let sampleIndex = 0; sampleIndex < channel.length; sampleIndex += 1) {
      mono[sampleIndex] += channel[sampleIndex] / audioBuffer.numberOfChannels;
    }
  }
  return mono;
}

function downsampleToTargetRate(
  input: Float32Array,
  inputSampleRate: number,
): Float32Array {
  if (inputSampleRate === SEGMENTATION_CONFIG.vadSampleRate) {
    return input.slice();
  }

  const ratio = inputSampleRate / SEGMENTATION_CONFIG.vadSampleRate;
  const outputLength = Math.max(1, Math.floor(input.length / ratio));
  const output = new Float32Array(outputLength);
  let sourceIndex = 0;

  for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
    const nextSourceIndex = Math.min(
      input.length,
      Math.floor((outputIndex + 1) * ratio),
    );
    let sum = 0;
    let count = 0;
    for (let index = Math.floor(sourceIndex); index < nextSourceIndex; index += 1) {
      sum += input[index];
      count += 1;
    }
    output[outputIndex] = count > 0 ? sum / count : input[Math.floor(sourceIndex)] ?? 0;
    sourceIndex = nextSourceIndex;
  }

  return output;
}

function applyHysteresis(previousState: boolean, probability: number): boolean {
  if (previousState) {
    return probability >= SEGMENTATION_CONFIG.negativeSpeechThreshold;
  }
  return probability >= SEGMENTATION_CONFIG.speechThreshold;
}

async function initWorker(worker: Worker): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      reject(new Error("vad_init_timeout"));
    }, SEGMENTATION_CONFIG.vadInitTimeoutMs);

    const handleMessage = (event: MessageEvent<WorkerOutbound>) => {
      if (event.data.type === "ready") {
        window.clearTimeout(timeoutId);
        worker.removeEventListener("message", handleMessage);
        resolve();
      }
      if (event.data.type === "error") {
        window.clearTimeout(timeoutId);
        worker.removeEventListener("message", handleMessage);
        reject(new Error(event.data.message));
      }
    };

    worker.addEventListener("message", handleMessage);
    worker.postMessage({
      type: "init",
      modelUrl: MODEL_URL,
    } satisfies WorkerInbound);
  });
}

async function runSmokeInference(worker: Worker): Promise<void> {
  const response = await new Promise<WorkerOutbound>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      reject(new Error("smoke_inference_timeout"));
    }, SEGMENTATION_CONFIG.vadInitTimeoutMs);

    const handleMessage = (event: MessageEvent<WorkerOutbound>) => {
      if (event.data.type === "frame" || event.data.type === "error") {
        window.clearTimeout(timeoutId);
        worker.removeEventListener("message", handleMessage);
        resolve(event.data);
      }
    };

    worker.addEventListener("message", handleMessage);
    worker.postMessage({ type: "smoke_infer" } satisfies WorkerInbound);
  });

  if (response.type === "error") {
    throw new Error(response.message);
  }
}

async function decodeBlobToPcm(blob: Blob): Promise<{
  samples: Float32Array;
  durationMs: number;
}> {
  const arrayBuffer = await blob.arrayBuffer();
  const AudioContextCtor = getAudioContextCtor();
  const audioContext = new AudioContextCtor();

  try {
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0));
    const mono = mixToMono(audioBuffer);
    return {
      samples: downsampleToTargetRate(mono, audioBuffer.sampleRate),
      durationMs: Math.round(audioBuffer.duration * 1000),
    };
  } finally {
    void audioContext.close().catch(() => undefined);
  }
}

export async function analyzeUploadedAudioWithSilero(
  blob: Blob,
): Promise<UploadedAudioFrontendAnalysis> {
  const { samples, durationMs } = await decodeBlobToPcm(blob);
  const worker = new Worker(new URL("./sileroVad.worker.ts", import.meta.url), {
    type: "module",
  });

  try {
    await initWorker(worker);
    await runSmokeInference(worker);

    const frames = await new Promise<WorkerOutbound[]>((resolve, reject) => {
      const collectedFrames: WorkerOutbound[] = [];
      let resolved = false;
      let pendingFrames = 0;

      const finalizeIfIdle = () => {
        if (resolved || pendingFrames > 0) {
          return;
        }
        resolved = true;
        worker.removeEventListener("message", handleMessage);
        resolve(collectedFrames);
      };

      const handleMessage = (event: MessageEvent<WorkerOutbound>) => {
        if (event.data.type === "error") {
          if (!resolved) {
            resolved = true;
            worker.removeEventListener("message", handleMessage);
            reject(new Error(event.data.message));
          }
          return;
        }

        if (event.data.type === "frame") {
          collectedFrames.push(event.data);
          pendingFrames = Math.max(0, pendingFrames - 1);
          window.setTimeout(finalizeIfIdle, 0);
        }
      };

      worker.addEventListener("message", handleMessage);

      const frameDurationMs =
        (SEGMENTATION_CONFIG.vadWindowSamples / SEGMENTATION_CONFIG.vadSampleRate) *
        1000;

      for (
        let sampleIndex = 0, frameIndex = 0;
        sampleIndex + SEGMENTATION_CONFIG.vadWindowSamples <= samples.length;
        sampleIndex += SEGMENTATION_CONFIG.vadWindowSamples, frameIndex += 1
      ) {
        pendingFrames += 1;
        worker.postMessage({
          type: "pcm_chunk",
          samples: samples.slice(
            sampleIndex,
            sampleIndex + SEGMENTATION_CONFIG.vadWindowSamples,
          ),
          timestampMs: Math.round(frameIndex * frameDurationMs),
          durationMs: frameDurationMs,
        } satisfies WorkerInbound);
      }

      window.setTimeout(finalizeIfIdle, 0);
    });

    let speechIntervals: SpeechInterval[] = [];
    let speechDurationMs = 0;
    let speechFrameCount = 0;
    let isSpeechState = false;

    for (const frame of frames) {
      if (frame.type !== "frame") {
        continue;
      }

      const isSpeech = applyHysteresis(isSpeechState, frame.speechProbability);
      isSpeechState = isSpeech;
      if (!isSpeech) {
        continue;
      }

      speechFrameCount += 1;
      speechDurationMs += frame.durationMs;
      const frameStartMs = Math.max(0, frame.timestampMs);
      const frameEndMs = Math.max(frameStartMs, frame.timestampMs + frame.durationMs);
      speechIntervals = appendSpeechFrame(speechIntervals, frameStartMs, frameEndMs);
    }

    const mergedSpeechIntervals = mergeSpeechIntervals(speechIntervals)
      .map((interval) => ({
        startMs: Math.max(0, Math.min(Math.round(interval.startMs), durationMs)),
        endMs: Math.max(0, Math.min(Math.round(interval.endMs), durationMs)),
      }))
      .filter((interval) => interval.endMs > interval.startMs);
    const removableSilences = detectRemovableSilences(
      mergedSpeechIntervals,
      durationMs,
    ).map((interval) => ({
      startMs: Math.round(interval.startMs),
      endMs: Math.round(interval.endMs),
    }));

    return {
      sectionDurationMs: durationMs,
      speechDurationMs: Math.round(speechDurationMs),
      speechFrameCount,
      hasDetectedSpeech: speechDurationMs > 0,
      speechIntervals: mergedSpeechIntervals,
      removableSilences,
      retainedIntervals: buildRetainedIntervals(removableSilences, durationMs),
    };
  } finally {
    worker.postMessage({ type: "destroy" } satisfies WorkerInbound);
    worker.terminate();
  }
}
