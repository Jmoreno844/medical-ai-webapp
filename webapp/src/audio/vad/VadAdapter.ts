export interface VadFrame {
  timestampMs: number;
  durationMs: number;
  speechProbability: number;
  isSpeech: boolean;
}

export type Unsubscribe = () => void;

export interface VadAdapter {
  initialize(stream: MediaStream): Promise<void>;
  start(): Promise<void>;
  pause(): void;
  resume(): void;
  destroy(): Promise<void>;

  onFrame(callback: (frame: VadFrame) => void): Unsubscribe;

  isAvailable(): boolean;
  getModelVersion(): string | undefined;
}
