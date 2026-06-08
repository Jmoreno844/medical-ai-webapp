import { SEGMENTATION_CONFIG } from "../segmentation/segmentationConfig";
import type { Unsubscribe, VadAdapter, VadFrame } from "./VadAdapter";

type BrowserAudioContextCtor = typeof AudioContext & {
  new (): AudioContext;
};

export class FallbackVadAdapter implements VadAdapter {
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private buffer: Float32Array | null = null;
  private intervalId: number | null = null;
  private sessionStartMs = 0;
  private frameCallbacks: Array<(frame: VadFrame) => void> = [];
  private isSpeechState = false;
  private isPaused = false;

  async initialize(stream: MediaStream): Promise<void> {
    const AudioContextCtor = (window.AudioContext ??
      (window as Window & { webkitAudioContext?: BrowserAudioContextCtor })
        .webkitAudioContext) as BrowserAudioContextCtor | undefined;

    if (!AudioContextCtor) {
      throw new Error("AudioContext not supported");
    }

    this.audioContext = new AudioContextCtor();
    this.sourceNode = this.audioContext.createMediaStreamSource(stream);
    this.analyser = this.audioContext.createAnalyser();
    this.analyser.fftSize = SEGMENTATION_CONFIG.fallbackVadAnalyserFftSize;
    this.analyser.smoothingTimeConstant = 0.15;
    const muteGain = this.audioContext.createGain();
    muteGain.gain.value = 0;
    this.sourceNode.connect(this.analyser);
    this.analyser.connect(muteGain);
    muteGain.connect(this.audioContext.destination);
    this.buffer = new Float32Array(this.analyser.fftSize);
    await this.audioContext.resume();
  }

  async start(): Promise<void> {
    this.sessionStartMs = performance.now();
    this.isPaused = false;
    this.intervalId = window.setInterval(() => {
      this.poll();
    }, SEGMENTATION_CONFIG.fallbackVadPollIntervalMs);
  }

  pause(): void {
    this.isPaused = true;
    if (this.intervalId !== null) {
      window.clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  resume(): void {
    if (!this.isPaused) {
      return;
    }
    this.isPaused = false;
    this.intervalId = window.setInterval(() => {
      this.poll();
    }, SEGMENTATION_CONFIG.fallbackVadPollIntervalMs);
  }

  async destroy(): Promise<void> {
    if (this.intervalId !== null) {
      window.clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.sourceNode?.disconnect();
    this.analyser?.disconnect();
    this.sourceNode = null;
    this.analyser = null;
    this.buffer = null;
    if (this.audioContext && this.audioContext.state !== "closed") {
      void this.audioContext.close().catch(() => undefined);
    }
    this.audioContext = null;
    this.frameCallbacks = [];
  }

  onFrame(callback: (frame: VadFrame) => void): Unsubscribe {
    this.frameCallbacks.push(callback);
    return () => {
      this.frameCallbacks = this.frameCallbacks.filter((item) => item !== callback);
    };
  }

  isAvailable(): boolean {
    return true;
  }

  getModelVersion(): string | undefined {
    return undefined;
  }

  private poll(): void {
    if (this.isPaused || !this.analyser || !this.buffer) {
      return;
    }

    this.analyser.getFloatTimeDomainData(this.buffer);
    let sumSquares = 0;
    let peak = 0;
    for (const sample of this.buffer) {
      const absoluteValue = Math.abs(sample);
      sumSquares += sample * sample;
      if (absoluteValue > peak) {
        peak = absoluteValue;
      }
    }
    const rms = Math.sqrt(sumSquares / this.buffer.length);
    const rawSpeech =
      rms >= SEGMENTATION_CONFIG.fallbackVadRmsThreshold ||
      peak >= SEGMENTATION_CONFIG.fallbackVadPeakThreshold;

    const probability = Math.min(1, Math.max(rms * 10, peak));
    const isSpeech = this.applyHysteresis(rawSpeech, probability);

    const timestampMs = performance.now() - this.sessionStartMs;
    const frame: VadFrame = {
      timestampMs,
      durationMs: SEGMENTATION_CONFIG.fallbackVadPollIntervalMs,
      speechProbability: probability,
      isSpeech,
    };

    this.frameCallbacks.forEach((callback) => callback(frame));
  }

  private applyHysteresis(rawSpeech: boolean, probability: number): boolean {
    if (rawSpeech && probability >= SEGMENTATION_CONFIG.speechThreshold) {
      this.isSpeechState = true;
      return true;
    }
    if (
      !rawSpeech ||
      probability < SEGMENTATION_CONFIG.negativeSpeechThreshold
    ) {
      this.isSpeechState = false;
      return false;
    }
    return this.isSpeechState;
  }
}
