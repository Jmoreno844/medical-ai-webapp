import { getBestSupportedAudioType } from "@/features/encuentroHeader/hooks/audio/utils";
import { createChildLogger } from "@/lib/logger";
import { SpeechSegmenter } from "../segmentation/SpeechSegmenter";
import { SEGMENTATION_CONFIG } from "../segmentation/segmentationConfig";
import {
  detectRemovableSilences,
  mergeSpeechIntervals,
} from "../segmentation/speechIntervals";
import type {
  AudioSectionMetadata,
  SectionCutSignal,
  SegmentState,
} from "../segmentation/types";
import type { VadAdapter } from "../vad/VadAdapter";
import { FallbackVadAdapter } from "../vad/FallbackVadAdapter";
import { analyzeUploadedAudioWithSilero } from "../vad/analyzeUploadedAudioWithSilero";

const logger = createChildLogger("AudioRecorderController");

type RecorderSection = {
  id: string;
  recorder: MediaRecorder;
  chunks: Blob[];
  startedAtMs: number;
  overlapMs: number;
};

export type AudioRecorderStartOptions = {
  preferredDeviceId?: string | null;
  initialElapsedMs?: number;
  collectFullSessionAudio?: boolean;
};

export type CompletedSessionAudio = {
  blob: Blob;
  url: string;
  durationMs: number;
  mimeType: string;
};

export type RecordedSection = {
  blob: Blob;
  url: string;
  startTimeMs: number;
  endTimeMs: number;
  metadata: AudioSectionMetadata;
};

export type LiveRecordingState = {
  isInitializing: boolean;
  isRecording: boolean;
  isPaused: boolean;
  segmentState: SegmentState;
  wallClockDurationMs: number;
  speechDurationMs: number;
  currentSilenceMs: number;
  sectionCount: number;
  vadAvailable: boolean;
  usedFallback: boolean;
  initWarning?: string;
  lastSpeechProbability?: number;
};

type StateListener = (state: LiveRecordingState) => void;
type SectionListener = (section: RecordedSection) => void;
type SessionAudioListener = (audio: CompletedSessionAudio) => void;

export class AudioRecorderController {
  private stream: MediaStream | null = null;
  private vadAdapter: VadAdapter | null = null;
  private segmenter = new SpeechSegmenter();
  private mimeType = "audio/webm";
  private sessionStartMs = 0;
  private pausedAtMs: number | null = null;
  private totalPausedMs = 0;
  private sequence = 0;
  private sections: RecordedSection[] = [];
  private activeSection: RecorderSection | null = null;
  private retiringSection: RecorderSection | null = null;
  private forcedSplitInFlight = false;
  private overlapTimerId: ReturnType<typeof setTimeout> | null = null;
  private vadUnsubscribe: (() => void) | null = null;
  private isRecording = false;
  private isPaused = false;
  private usedFallback = false;
  private initWarning: string | undefined;
  private lastSpeechProbability: number | undefined;
  private stateListeners: StateListener[] = [];
  private sectionListeners: SectionListener[] = [];
  private sectionFlushChain: Promise<void> = Promise.resolve();
  private isInitializing = false;
  private publishThrottleTimer: ReturnType<typeof setTimeout> | null = null;
  private sessionTimerId: ReturnType<typeof setInterval> | null = null;
  private isStopping = false;
  private lastSessionElapsedMs = 0;
  private cleanupPromise: Promise<void> | null = null;
  private fullSessionRecorder: MediaRecorder | null = null;
  private fullSessionChunks: Blob[] = [];
  private collectFullSessionAudio = false;
  private sessionAudioListeners: SessionAudioListener[] = [];

  onStateChange(listener: StateListener): () => void {
    this.stateListeners.push(listener);
    listener(this.getLiveStateInternal());
    return () => {
      this.stateListeners = this.stateListeners.filter((item) => item !== listener);
    };
  }

  onSectionRecorded(listener: SectionListener): () => void {
    this.sectionListeners.push(listener);
    return () => {
      this.sectionListeners = this.sectionListeners.filter(
        (item) => item !== listener,
      );
    };
  }

  onSessionAudioReady(listener: SessionAudioListener): () => void {
    this.sessionAudioListeners.push(listener);
    return () => {
      this.sessionAudioListeners = this.sessionAudioListeners.filter(
        (item) => item !== listener,
      );
    };
  }

  getSections(): RecordedSection[] {
    return [...this.sections];
  }

  getLiveState(): LiveRecordingState {
    return this.getLiveStateInternal();
  }

  async start(options: AudioRecorderStartOptions = {}): Promise<void> {
    if (this.isRecording || this.isInitializing) {
      return;
    }
    if (this.cleanupPromise) {
      await this.cleanupPromise;
    }

    this.isInitializing = true;
    this.schedulePublishState();

    try {
      const audioConstraints: MediaStreamConstraints = {
        audio: {
          channelCount: 1,
          sampleRate: SEGMENTATION_CONFIG.vadSampleRate,
          echoCancellation: true,
          noiseSuppression: true,
          ...(options.preferredDeviceId
            ? { deviceId: { exact: options.preferredDeviceId } }
            : {}),
        },
      };

      try {
        this.stream = await navigator.mediaDevices.getUserMedia(audioConstraints);
      } catch (error) {
        if (!options.preferredDeviceId) {
          throw error;
        }
        this.stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            sampleRate: SEGMENTATION_CONFIG.vadSampleRate,
            echoCancellation: true,
            noiseSuppression: true,
          },
        });
      }
      this.mimeType = getBestSupportedAudioType();
      this.sessionStartMs = performance.now() - (options.initialElapsedMs ?? 0);
      this.totalPausedMs = 0;
      this.pausedAtMs = null;
      this.sequence = 0;
      this.sections = [];
      this.lastSessionElapsedMs = 0;
      this.usedFallback = false;
      this.initWarning = undefined;
      this.collectFullSessionAudio = options.collectFullSessionAudio ?? false;
      this.fullSessionChunks = [];

      if (this.collectFullSessionAudio && this.stream) {
        this.startFullSessionRecorder();
      }

      const energyVad = new FallbackVadAdapter();
      await energyVad.initialize(this.stream);
      await energyVad.start();
      this.vadAdapter = energyVad;

      this.segmenter.start(!this.usedFallback);

      this.vadUnsubscribe = this.vadAdapter.onFrame((frame) => {
        this.lastSpeechProbability = frame.speechProbability;
        const cut = this.segmenter.processFrame(frame);
        if (cut) {
          void this.handleSectionCut(cut);
        }
        this.schedulePublishState();
      });

      this.isRecording = true;
      this.isPaused = false;
      this.startActiveSection(0);
      this.startSessionTimer();
    } finally {
      this.isInitializing = false;
      this.schedulePublishState();
    }
  }

  pause(): void {
    if (!this.isRecording || this.isPaused) {
      return;
    }
    this.isPaused = true;
    this.pausedAtMs = performance.now();
    this.segmenter.setPaused(true);
    this.vadAdapter?.pause();
    if (this.activeSection?.recorder.state === "recording") {
      this.activeSection.recorder.pause();
    }
    if (this.forcedSplitInFlight) {
      void this.finalizeRetiringSection();
    }
    this.publishState();
  }

  resume(): void {
    if (!this.isRecording || !this.isPaused) {
      return;
    }
    if (this.pausedAtMs !== null) {
      this.totalPausedMs += performance.now() - this.pausedAtMs;
      this.pausedAtMs = null;
    }
    this.isPaused = false;
    this.segmenter.setPaused(false);
    this.vadAdapter?.resume();
    if (this.activeSection?.recorder.state === "paused") {
      this.activeSection.recorder.resume();
    } else if (!this.activeSection && this.stream?.active) {
      this.startActiveSection(0);
    }
    this.publishState();
  }

  async stop(): Promise<RecordedSection | null> {
    if (!this.isRecording || this.isStopping) {
      return null;
    }
    const stopStartedAt = performance.now();

    this.isStopping = true;
    this.lastSessionElapsedMs = this.getElapsedMs();
    this.isRecording = false;
    this.isPaused = false;
    this.stopSessionTimer();
    this.segmenter.setPaused(false);
    this.vadAdapter?.pause();
    this.publishState();

    try {
      if (this.forcedSplitInFlight) {
        logger.debug("[AudioRecorder] stop(): finalizing retiring section");
        await this.finalizeRetiringSection();
      }

      const manualCut = this.segmenter.stop();
      let finalSection: RecordedSection | null = null;
      if (manualCut) {
        logger.debug("[AudioRecorder] stop(): handling manual cut", {
          wallClockDurationMs: manualCut.wallClockDurationMs,
          speechDurationMs: manualCut.speechDurationMs,
        });
        finalSection = await this.withTimeout(
          this.handleSectionCut(manualCut, true),
          5_000,
          null,
        );
      } else {
        logger.debug("[AudioRecorder] stop(): flushing active section without speech cut");
        await this.withTimeout(this.flushActiveSection(true), 5_000, undefined);
      }

      const completedSessionAudio = this.collectFullSessionAudio
        ? await this.withTimeout(
            this.stopFullSessionRecorder(this.lastSessionElapsedMs),
            3_000,
            null,
          )
        : null;
      if (completedSessionAudio) {
        this.sessionAudioListeners.forEach((listener) => listener(completedSessionAudio));
      }

      this.cleanupPromise = this.cleanup().finally(() => {
        logger.debug("[AudioRecorder] stop(): background cleanup finished", {
          totalStopMs: Math.round(performance.now() - stopStartedAt),
        });
        this.cleanupPromise = null;
        this.publishState();
      });
      logger.debug("[AudioRecorder] stop(): returned control to UI", {
        totalStopMs: Math.round(performance.now() - stopStartedAt),
      });
      this.publishState();
      return finalSection;
    } finally {
      this.isStopping = false;
      this.publishState();
    }
  }

  async destroy(): Promise<void> {
    this.isRecording = false;
    await (this.cleanupPromise ?? this.cleanup());
    this.revokeSectionUrls();
    this.sections = [];
    this.publishState();
  }

  private getElapsedMs(): number {
    const now = performance.now();
    const pausedExtra =
      this.pausedAtMs !== null ? now - this.pausedAtMs : 0;
    return now - this.sessionStartMs - this.totalPausedMs - pausedExtra;
  }

  private getLiveStateInternal(): LiveRecordingState {
    const snapshot = this.segmenter.getSnapshot();
    if (this.isRecording || this.isPaused) {
      this.lastSessionElapsedMs = this.getElapsedMs();
    }
    return {
      isInitializing: this.isInitializing,
      isRecording: this.isRecording,
      isPaused: this.isPaused,
      segmentState: snapshot.state,
      wallClockDurationMs: Math.max(
        snapshot.wallClockDurationMs,
        this.lastSessionElapsedMs,
      ),
      speechDurationMs: snapshot.speechDurationMs,
      currentSilenceMs: snapshot.currentSilenceMs,
      sectionCount: this.sections.length,
      vadAvailable: snapshot.vadAvailable && !this.usedFallback,
      usedFallback: this.usedFallback,
      initWarning: this.initWarning,
      lastSpeechProbability: this.lastSpeechProbability,
    };
  }

  private publishState(): void {
    const state = this.getLiveStateInternal();
    this.stateListeners.forEach((listener) => listener(state));
  }

  private schedulePublishState(): void {
    if (this.publishThrottleTimer !== null) {
      return;
    }
    this.publishThrottleTimer = setTimeout(() => {
      this.publishThrottleTimer = null;
      this.publishState();
    }, 250);
  }

  private startSessionTimer(): void {
    this.stopSessionTimer();
    this.sessionTimerId = setInterval(() => {
      if (this.isRecording && !this.isPaused) {
        this.schedulePublishState();
      }
    }, 250);
  }

  private stopSessionTimer(): void {
    if (this.sessionTimerId !== null) {
      clearInterval(this.sessionTimerId);
      this.sessionTimerId = null;
    }
  }

  private withTimeout<T>(
    promise: Promise<T>,
    timeoutMs: number,
    fallback: T,
  ): Promise<T> {
    return Promise.race([
      promise,
      new Promise<T>((resolve) => {
        setTimeout(() => resolve(fallback), timeoutMs);
      }),
    ]);
  }

  private queueSectionWork(work: () => Promise<void>): Promise<void> {
    this.sectionFlushChain = this.sectionFlushChain
      .then(work)
      .catch((error) => {
        logger.error("[AudioRecorder] Section flush failed", error);
      });
    return this.sectionFlushChain;
  }

  private startActiveSection(overlapMs: number): void {
    if (!this.stream?.active) {
      return;
    }

    const recorder = new MediaRecorder(this.stream, {
      mimeType: this.mimeType,
      audioBitsPerSecond: 24000,
    });

    const section: RecorderSection = {
      id: crypto.randomUUID(),
      recorder,
      chunks: [],
      startedAtMs: this.getElapsedMs(),
      overlapMs,
    };

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        section.chunks.push(event.data);
      }
    };

    recorder.onerror = (event) => {
      logger.error("[AudioRecorder] MediaRecorder error", event);
    };

    recorder.start();
    this.activeSection = section;
  }

  private startFullSessionRecorder(): void {
    if (!this.stream?.active) {
      return;
    }

    const recorder = new MediaRecorder(this.stream, {
      mimeType: this.mimeType,
      audioBitsPerSecond: 24000,
    });
    this.fullSessionChunks = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        this.fullSessionChunks.push(event.data);
      }
    };
    recorder.start();
    this.fullSessionRecorder = recorder;
  }

  private async stopFullSessionRecorder(
    durationMs: number,
  ): Promise<CompletedSessionAudio | null> {
    const recorder = this.fullSessionRecorder;
    if (!recorder) {
      return null;
    }

    const buildAudio = (): CompletedSessionAudio | null => {
      if (this.fullSessionChunks.length === 0) {
        return null;
      }
      const blob = new Blob(this.fullSessionChunks, {
        type: recorder.mimeType || this.mimeType,
      });
      this.fullSessionChunks = [];
      const url = URL.createObjectURL(blob);
      return {
        blob,
        url,
        durationMs,
        mimeType: blob.type || this.mimeType,
      };
    };

    if (recorder.state === "inactive") {
      this.fullSessionRecorder = null;
      return buildAudio();
    }

    return new Promise((resolve) => {
      let settled = false;

      const settle = () => {
        if (settled) return;
        settled = true;
        this.fullSessionRecorder = null;
        resolve(buildAudio());
      };

      recorder.onstop = settle;
      const timeoutId = setTimeout(() => {
        clearTimeout(timeoutId);
        settle();
      }, 2500);

      try {
        if (recorder.state === "paused") {
          recorder.resume();
        }
        if (recorder.state !== "inactive") {
          recorder.requestData();
        }
        recorder.stop();
      } catch {
        clearTimeout(timeoutId);
        settle();
      }
    });
  }

  private async stopSectionRecorder(
    section: RecorderSection,
  ): Promise<{ blob: Blob | null; endTimeMs: number }> {
    const mediaRecorder = section.recorder;
    if (mediaRecorder.state === "inactive") {
      const endTimeMs = this.getElapsedMs();
      return {
        blob:
          section.chunks.length > 0
            ? new Blob(section.chunks, {
                type: mediaRecorder.mimeType || this.mimeType,
              })
            : null,
        endTimeMs,
      };
    }

    return new Promise((resolve) => {
      let settled = false;
      const mimeType = mediaRecorder.mimeType || this.mimeType;

      const settle = () => {
        if (settled) return;
        settled = true;
        const endTimeMs = this.getElapsedMs();
        const blob =
          section.chunks.length > 0
            ? new Blob(section.chunks, { type: mimeType })
            : null;
        section.chunks = [];
        resolve({ blob, endTimeMs });
      };

      mediaRecorder.onstop = settle;
      const timeoutId = setTimeout(settle, 2500);

      try {
        if (mediaRecorder.state === "paused") {
          mediaRecorder.resume();
        }
        if (mediaRecorder.state !== "inactive") {
          mediaRecorder.requestData();
        }
        mediaRecorder.stop();
      } catch {
        clearTimeout(timeoutId);
        settle();
      }
    });
  }

  private handleSectionCut(
    signal: SectionCutSignal,
    isFinal = false,
  ): Promise<RecordedSection | null> {
    if (signal.forcedCut && !isFinal) {
      return this.splitWithOverlap(signal);
    }

    return new Promise((resolve) => {
      void this.queueSectionWork(async () => {
        const recorded = await this.finalizeActiveSection(signal);
        if (
          !isFinal &&
          this.isRecording &&
          !this.isPaused &&
          this.stream?.active
        ) {
          this.startActiveSection(0);
        }
        resolve(recorded);
      });
    });
  }

  private async splitWithOverlap(
    signal: SectionCutSignal,
  ): Promise<RecordedSection | null> {
    if (!this.stream?.active || !this.activeSection || this.forcedSplitInFlight) {
      return null;
    }

    this.forcedSplitInFlight = true;
    this.retiringSection = this.activeSection;
    this.activeSection = null;
    this.startActiveSection(signal.overlapBeforeMs);

    return new Promise((resolve) => {
      if (this.overlapTimerId) {
        clearTimeout(this.overlapTimerId);
      }
      this.overlapTimerId = setTimeout(() => {
        this.overlapTimerId = null;
        void this.queueSectionWork(async () => {
          const recorded = await this.finalizeRetiringSectionWithSignal(signal);
          this.forcedSplitInFlight = false;
          resolve(recorded);
        });
      }, SEGMENTATION_CONFIG.forcedCutOverlapMs);
    });
  }

  private async finalizeRetiringSection(): Promise<void> {
    const signal =
      this.segmenter.buildSnapshotCutSignal(
        "forced_maximum",
        true,
        SEGMENTATION_CONFIG.forcedCutOverlapMs,
      ) ?? {
        cutReason: "forced_maximum" as const,
        forcedCut: true,
        overlapBeforeMs: SEGMENTATION_CONFIG.forcedCutOverlapMs,
        wallClockDurationMs: 0,
        speechDurationMs: 0,
        speechIntervals: [],
        removableSilences: [],
      };
    await this.finalizeRetiringSectionWithSignal(signal);
    this.forcedSplitInFlight = false;
  }

  private async finalizeRetiringSectionWithSignal(
    signal: SectionCutSignal,
  ): Promise<RecordedSection | null> {
    const section = this.retiringSection;
    this.retiringSection = null;
    if (!section) {
      return null;
    }
    return this.buildRecordedSection(section, signal);
  }

  private async finalizeActiveSection(
    signal: SectionCutSignal,
  ): Promise<RecordedSection | null> {
    const section = this.activeSection;
    this.activeSection = null;
    if (!section) {
      return null;
    }
    return this.buildRecordedSection(section, signal);
  }

  private async flushActiveSection(isFinal: boolean): Promise<void> {
    const section = this.activeSection;
    if (!section) {
      return;
    }
    this.activeSection = null;
    const signal = this.segmenter.buildSnapshotCutSignal(
      isFinal ? "manual_stop" : "silence_after_minimum",
      false,
      0,
    );
    if (!signal) {
      await this.stopSectionRecorder(section);
      return;
    }
    await this.buildRecordedSection(section, signal);
  }

  private async buildRecordedSection(
    section: RecorderSection,
    signal: SectionCutSignal,
  ): Promise<RecordedSection | null> {
    const { blob, endTimeMs } = await this.stopSectionRecorder(section);
    if (!blob || blob.size === 0) {
      return null;
    }

    // MediaRecorder can include a little more trailing audio than the last VAD frame
    // we processed before stop(). Use the real recorded duration so final silence
    // candidates are not dropped on manual stop.
    const recordedDurationMs = Math.max(
      0,
      Math.round(endTimeMs - section.startedAtMs),
    );
    const normalizedWallClockDurationMs = Math.max(
      Math.round(signal.wallClockDurationMs),
      recordedDurationMs,
    );
    const finalVad = await this.buildFinalVadMetadata(
      blob,
      signal,
      normalizedWallClockDurationMs,
    );

    const metadata: AudioSectionMetadata = {
      sectionId: section.id,
      sequence: this.sequence,
      wallClockDurationMs: finalVad.wallClockDurationMs,
      speechDurationMs: finalVad.speechDurationMs,
      speechIntervals: finalVad.speechIntervals,
      removableSilences: finalVad.removableSilences,
      cutReason: signal.cutReason,
      forcedCut: signal.forcedCut,
      overlapBeforeMs: section.overlapMs,
      vadAvailable: !this.usedFallback,
      vadModelVersion: this.vadAdapter?.getModelVersion(),
      audioMimeType: blob.type || this.mimeType,
    };

    const url = URL.createObjectURL(blob);
    const recorded: RecordedSection = {
      blob,
      url,
      startTimeMs: section.startedAtMs,
      endTimeMs,
      metadata,
    };
    this.sections.push(recorded);
    this.sequence += 1;
    this.sectionListeners.forEach((listener) => listener(recorded));
    this.publishState();
    return recorded;
  }

  private async buildFinalVadMetadata(
    blob: Blob,
    signal: SectionCutSignal,
    normalizedWallClockDurationMs: number,
  ): Promise<{
    wallClockDurationMs: number;
    speechDurationMs: number;
    speechIntervals: AudioSectionMetadata["speechIntervals"];
    removableSilences: AudioSectionMetadata["removableSilences"];
  }> {
    try {
      const analysis = await analyzeUploadedAudioWithSilero(blob);
      return {
        wallClockDurationMs: Math.max(
          analysis.sectionDurationMs,
          normalizedWallClockDurationMs,
        ),
        speechDurationMs: analysis.speechDurationMs,
        speechIntervals: analysis.speechIntervals,
        removableSilences: analysis.removableSilences,
      };
    } catch (error) {
      logger.warn("[AudioRecorder] Final offline VAD analysis failed", {
        error: error instanceof Error ? error.message : "unknown_error",
      });
    }

    const speechIntervals = mergeSpeechIntervals(signal.speechIntervals)
      .map((interval) => ({
        startMs: Math.max(
          0,
          Math.min(Math.round(interval.startMs), normalizedWallClockDurationMs),
        ),
        endMs: Math.max(
          0,
          Math.min(Math.round(interval.endMs), normalizedWallClockDurationMs),
        ),
      }))
      .filter((interval) => interval.endMs > interval.startMs);
    const removableSilences = detectRemovableSilences(
      speechIntervals,
      normalizedWallClockDurationMs,
    );

    return {
      wallClockDurationMs: normalizedWallClockDurationMs,
      speechDurationMs: signal.speechDurationMs,
      speechIntervals,
      removableSilences,
    };
  }

  private revokeSectionUrls(): void {
    for (const section of this.sections) {
      URL.revokeObjectURL(section.url);
    }
  }

  private async cleanup(): Promise<void> {
    this.stopSessionTimer();

    if (this.overlapTimerId) {
      clearTimeout(this.overlapTimerId);
      this.overlapTimerId = null;
    }

    if (this.publishThrottleTimer !== null) {
      clearTimeout(this.publishThrottleTimer);
      this.publishThrottleTimer = null;
    }

    this.vadUnsubscribe?.();
    this.vadUnsubscribe = null;

    if (this.activeSection) {
      await this.stopSectionRecorder(this.activeSection);
      this.activeSection = null;
    }
    if (this.retiringSection) {
      await this.stopSectionRecorder(this.retiringSection);
      this.retiringSection = null;
    }
    if (this.fullSessionRecorder) {
      await this.stopFullSessionRecorder(this.lastSessionElapsedMs);
    }

    await this.vadAdapter?.destroy();
    this.vadAdapter = null;

    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }
}
