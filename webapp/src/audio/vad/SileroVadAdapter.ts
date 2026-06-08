import { createChildLogger } from "@/lib/logger";
import { SEGMENTATION_CONFIG } from "../segmentation/segmentationConfig";
import { FallbackVadAdapter } from "./FallbackVadAdapter";
import type { Unsubscribe, VadAdapter, VadFrame } from "./VadAdapter";

type BrowserAudioContextCtor = typeof AudioContext & {
  new (options?: AudioContextOptions): AudioContext;
};

const MODEL_URL = "/vad/silero_vad.onnx";
const CHUNK_LOG_EVERY = 50;
const FRAME_LOG_EVERY = 25;

const logger = createChildLogger("SileroVadAdapter");

type WorkerOutbound =
  | { type: "ready" }
  | { type: "error"; message: string }
  | {
      type: "frame";
      timestampMs: number;
      durationMs: number;
      speechProbability: number;
    };

export class SileroVadAdapter implements VadAdapter {
  private audioContext: AudioContext | null = null;
  private processorNode: ScriptProcessorNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private worker: Worker | null = null;
  private muteGainNode: GainNode | null = null;
  private frameCallbacks: Array<(frame: VadFrame) => void> = [];
  private isSpeechState = false;
  private isPaused = false;
  private available = false;
  private sessionStartMs = 0;
  private chunkCount = 0;
  private frameCount = 0;
  private noChunkWarningTimer: ReturnType<typeof setTimeout> | null = null;
  private workerHandler: ((event: MessageEvent<WorkerOutbound>) => void) | null =
    null;
  private pendingPcmBuffer = new Float32Array(
    SEGMENTATION_CONFIG.vadWindowSamples * 8,
  );
  private pendingPcmLength = 0;

  async initialize(stream: MediaStream): Promise<void> {
    const AudioContextCtor = (window.AudioContext ??
      (window as Window & { webkitAudioContext?: BrowserAudioContextCtor })
        .webkitAudioContext) as BrowserAudioContextCtor | undefined;

    if (!AudioContextCtor) {
      throw new Error("AudioContext not supported");
    }

    this.worker = new Worker(
      new URL("./sileroVad.worker.ts", import.meta.url),
      { type: "module" },
    );
    logger.debug("Initializing worker");

    await this.initWorkerWithTimeout();
    await this.runSmokeInference();

    this.audioContext = new AudioContextCtor();
    logger.debug("Audio context created", {
      sampleRate: this.audioContext.sampleRate,
      baseLatency: this.audioContext.baseLatency,
    });

    this.sourceNode = this.audioContext.createMediaStreamSource(stream);
    this.processorNode = this.audioContext.createScriptProcessor(
      SEGMENTATION_CONFIG.vadScriptProcessorBufferSize,
      1,
      1,
    );
    this.processorNode.onaudioprocess = (event) => {
      if (this.isPaused || !this.worker) {
        return;
      }

      const inputChannel = event.inputBuffer.getChannelData(0);
      const outputChannel = event.outputBuffer.getChannelData(0);
      outputChannel.set(inputChannel);
      this.handleAudioProcess(inputChannel);
    };

    this.muteGainNode = this.audioContext.createGain();
    this.muteGainNode.gain.value = 0;

    this.workerHandler = (event: MessageEvent<WorkerOutbound>) => {
      if (this.isPaused || event.data.type !== "frame") {
        return;
      }

      const { timestampMs, durationMs, speechProbability } = event.data;
      const isSpeech = this.applyHysteresis(speechProbability);
      const frame: VadFrame = {
        timestampMs: timestampMs || performance.now() - this.sessionStartMs,
        durationMs,
        speechProbability,
        isSpeech,
      };
      this.frameCount += 1;
      if (this.frameCount === 1 || this.frameCount % FRAME_LOG_EVERY === 0) {
        logger.debug("VAD frame received from worker", {
          frameCount: this.frameCount,
          durationMs,
          speechProbability: Number(speechProbability.toFixed(4)),
          isSpeech,
          timestampMs: Math.round(frame.timestampMs),
        });
      }
      this.frameCallbacks.forEach((callback) => callback(frame));
    };
    this.worker.addEventListener("message", this.workerHandler);

    // ScriptProcessor must stay in a pulled graph to receive audioprocess callbacks.
    this.sourceNode.connect(this.processorNode);
    this.processorNode.connect(this.muteGainNode);
    this.muteGainNode.connect(this.audioContext.destination);

    await this.audioContext.resume();
    logger.debug("Audio context resumed", {
      bufferSize: this.processorNode.bufferSize,
    });
    this.available = true;
  }

  async start(): Promise<void> {
    this.sessionStartMs = performance.now();
    this.isPaused = false;
    this.chunkCount = 0;
    this.frameCount = 0;
    this.pendingPcmLength = 0;
    logger.debug("VAD start");
    this.armNoChunkWarningTimer();
  }

  pause(): void {
    this.isPaused = true;
    this.clearNoChunkWarningTimer();
    logger.debug("VAD paused", {
      chunkCount: this.chunkCount,
      frameCount: this.frameCount,
    });
  }

  resume(): void {
    this.isPaused = false;
    logger.debug("VAD resumed");
    this.armNoChunkWarningTimer();
  }

  async destroy(): Promise<void> {
    this.clearNoChunkWarningTimer();
    if (this.workerHandler && this.worker) {
      this.worker.removeEventListener("message", this.workerHandler);
    }
    this.workerHandler = null;

    if (this.processorNode) {
      this.processorNode.onaudioprocess = null;
    }

    this.sourceNode?.disconnect();
    this.processorNode?.disconnect();
    this.muteGainNode?.disconnect();
    this.sourceNode = null;
    this.processorNode = null;
    this.muteGainNode = null;

    if (this.worker) {
      this.worker.postMessage({ type: "destroy" });
      this.worker.terminate();
      this.worker = null;
    }

    if (this.audioContext && this.audioContext.state !== "closed") {
      logger.debug("Closing audio context");
      void this.audioContext.close().catch(() => undefined);
    }

    logger.debug("VAD destroyed", {
      chunkCount: this.chunkCount,
      frameCount: this.frameCount,
    });
    this.audioContext = null;
    this.frameCallbacks = [];
    this.available = false;
  }

  onFrame(callback: (frame: VadFrame) => void): Unsubscribe {
    this.frameCallbacks.push(callback);
    return () => {
      this.frameCallbacks = this.frameCallbacks.filter((item) => item !== callback);
    };
  }

  isAvailable(): boolean {
    return this.available;
  }

  getModelVersion(): string | undefined {
    return SEGMENTATION_CONFIG.vadModelVersion;
  }

  private initWorkerWithTimeout(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.worker) {
        reject(new Error("worker_missing"));
        return;
      }

      const timeoutId = window.setTimeout(() => {
        reject(new Error("vad_init_timeout"));
      }, SEGMENTATION_CONFIG.vadInitTimeoutMs);

      const handleMessage = (event: MessageEvent<WorkerOutbound>) => {
        if (event.data.type === "ready") {
          window.clearTimeout(timeoutId);
          this.worker?.removeEventListener("message", handleMessage);
          resolve();
        }
        if (event.data.type === "error") {
          window.clearTimeout(timeoutId);
          this.worker?.removeEventListener("message", handleMessage);
          reject(new Error(event.data.message));
        }
      };

      this.worker.addEventListener("message", handleMessage);
      this.worker.postMessage({
        type: "init",
        modelUrl: MODEL_URL,
      });
    });
  }

  private async runSmokeInference(): Promise<void> {
    if (!this.worker) {
      throw new Error("worker_missing");
    }

    const response = await new Promise<WorkerOutbound>((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        reject(new Error("smoke_inference_timeout"));
      }, SEGMENTATION_CONFIG.vadInitTimeoutMs);

      const handleMessage = (event: MessageEvent<WorkerOutbound>) => {
        if (event.data.type === "frame" || event.data.type === "error") {
          window.clearTimeout(timeoutId);
          this.worker?.removeEventListener("message", handleMessage);
          resolve(event.data);
        }
      };

      const worker = this.worker;
      if (!worker) {
        reject(new Error("worker_missing"));
        return;
      }

      worker.addEventListener("message", handleMessage);
      worker.postMessage({ type: "smoke_infer" });
    });

    if (response.type === "error") {
      throw new Error(response.message);
    }
  }

  private handleAudioProcess(inputChannel: Float32Array): void {
    const sampleRate = this.audioContext?.sampleRate ?? 0;
    if (sampleRate <= 0) {
      return;
    }

    const resampled = this.downsampleToTargetRate(inputChannel, sampleRate);
    if (resampled.length === 0) {
      return;
    }

    this.appendPendingPcm(resampled);
    while (this.pendingPcmLength >= SEGMENTATION_CONFIG.vadWindowSamples) {
      this.emitPcmChunk();
    }
  }

  private downsampleToTargetRate(
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

  private appendPendingPcm(samples: Float32Array): void {
    if (samples.length >= this.pendingPcmBuffer.length) {
      this.pendingPcmBuffer.set(
        samples.subarray(samples.length - this.pendingPcmBuffer.length),
      );
      this.pendingPcmLength = this.pendingPcmBuffer.length;
      return;
    }

    const requiredLength = this.pendingPcmLength + samples.length;
    if (requiredLength > this.pendingPcmBuffer.length) {
      const overflow = requiredLength - this.pendingPcmBuffer.length;
      this.pendingPcmBuffer.copyWithin(0, overflow, this.pendingPcmLength);
      this.pendingPcmLength -= overflow;
    }

    this.pendingPcmBuffer.set(samples, this.pendingPcmLength);
    this.pendingPcmLength += samples.length;
  }

  private emitPcmChunk(): void {
    if (!this.worker) {
      return;
    }

    const samples = this.pendingPcmBuffer.slice(0, SEGMENTATION_CONFIG.vadWindowSamples);
    const remaining = this.pendingPcmLength - SEGMENTATION_CONFIG.vadWindowSamples;
    if (remaining > 0) {
      this.pendingPcmBuffer.copyWithin(
        0,
        SEGMENTATION_CONFIG.vadWindowSamples,
        this.pendingPcmLength,
      );
    }
    this.pendingPcmLength = Math.max(0, remaining);

    this.clearNoChunkWarningTimer();
    this.chunkCount += 1;

    const durationMs =
      (SEGMENTATION_CONFIG.vadWindowSamples / SEGMENTATION_CONFIG.vadSampleRate) *
      1000;
    const timestampMs = performance.now() - this.sessionStartMs;

    if (this.chunkCount === 1 || this.chunkCount % CHUNK_LOG_EVERY === 0) {
      logger.debug("PCM chunk emitted from script processor", {
        chunkCount: this.chunkCount,
        durationMs,
        samples: samples.length,
        timestampMs: Math.round(timestampMs),
      });
    }

    this.worker.postMessage({
      type: "pcm_chunk",
      samples,
      timestampMs,
      durationMs,
    });
  }

  private applyHysteresis(probability: number): boolean {
    if (probability >= SEGMENTATION_CONFIG.speechThreshold) {
      this.isSpeechState = true;
      return true;
    }
    if (probability < SEGMENTATION_CONFIG.negativeSpeechThreshold) {
      this.isSpeechState = false;
      return false;
    }
    return this.isSpeechState;
  }

  private armNoChunkWarningTimer(): void {
    this.clearNoChunkWarningTimer();
    this.noChunkWarningTimer = setTimeout(() => {
      if (this.chunkCount === 0) {
        logger.warn("No PCM chunks received within 2s of start/resume");
      }
    }, 2_000);
  }

  private clearNoChunkWarningTimer(): void {
    if (this.noChunkWarningTimer !== null) {
      clearTimeout(this.noChunkWarningTimer);
      this.noChunkWarningTimer = null;
    }
  }
}

export async function createVadAdapter(
  stream: MediaStream,
): Promise<{ adapter: VadAdapter; usedFallback: boolean; initError?: string }> {
  const silero = new SileroVadAdapter();
  try {
    await silero.initialize(stream);
    await silero.start();
    return { adapter: silero, usedFallback: false };
  } catch (error) {
    await silero.destroy().catch(() => undefined);
    const fallback = new FallbackVadAdapter();
    await fallback.initialize(stream);
    await fallback.start();
    return {
      adapter: fallback,
      usedFallback: true,
      initError: error instanceof Error ? error.message : "vad_init_failed",
    };
  }
}
