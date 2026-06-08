import { useCallback, useEffect, useRef, useState } from "react";
import {
  AudioRecorderController,
  type AudioRecorderStartOptions,
  type CompletedSessionAudio,
  type LiveRecordingState,
  type RecordedSection,
} from "@/audio/recording/AudioRecorderController";

const UI_THROTTLE_MS = 250;

const INITIAL_STATE: LiveRecordingState = {
  isInitializing: false,
  isRecording: false,
  isPaused: false,
  segmentState: "stopped",
  wallClockDurationMs: 0,
  speechDurationMs: 0,
  currentSilenceMs: 0,
  sectionCount: 0,
  vadAvailable: false,
  usedFallback: false,
};

type UseSpeechSegmentedRecorderOptions = {
  controllerStartOptions?: AudioRecorderStartOptions;
};

export function useSpeechSegmentedRecorder(
  options: UseSpeechSegmentedRecorderOptions = {},
) {
  const controllerRef = useRef<AudioRecorderController | null>(null);
  const [liveState, setLiveState] = useState<LiveRecordingState>(INITIAL_STATE);
  const [sections, setSections] = useState<RecordedSection[]>([]);
  const [sessionAudio, setSessionAudio] = useState<CompletedSessionAudio | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const lastUiUpdateRef = useRef(0);

  useEffect(() => {
    const controller = new AudioRecorderController();
    controllerRef.current = controller;

    const unsubscribeState = controller.onStateChange((state) => {
      const now = performance.now();
      if (
        now - lastUiUpdateRef.current < UI_THROTTLE_MS &&
        state.isRecording &&
        !state.isInitializing
      ) {
        return;
      }
      lastUiUpdateRef.current = now;
      setLiveState(state);
    });

    const unsubscribeSections = controller.onSectionRecorded((section) => {
      setSections((current) => [...current, section]);
      setLiveState(controller.getLiveState());
    });
    const unsubscribeSessionAudio = controller.onSessionAudioReady((audio) => {
      setSessionAudio((current) => {
        if (current) {
          URL.revokeObjectURL(current.url);
        }
        return audio;
      });
    });

    return () => {
      unsubscribeState();
      unsubscribeSections();
      unsubscribeSessionAudio();
      void controller.destroy();
      controllerRef.current = null;
    };
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    setSections([]);
    setSessionAudio((current) => {
      if (current) {
        URL.revokeObjectURL(current.url);
      }
      return null;
    });
    setLiveState((current) => ({ ...current, isInitializing: true }));
    try {
      await controllerRef.current?.start(options.controllerStartOptions);
      setLiveState(controllerRef.current?.getLiveState() ?? INITIAL_STATE);
    } catch (startError) {
      setLiveState((current) => ({ ...current, isInitializing: false }));
      setError(
        startError instanceof Error
          ? startError.message
          : "No se pudo iniciar la grabación.",
      );
    }
  }, [options.controllerStartOptions]);

  const stopRecording = useCallback(async () => {
    setLiveState((current) => ({
      ...current,
      isRecording: false,
      isPaused: false,
    }));
    try {
      await controllerRef.current?.stop();
      setLiveState(controllerRef.current?.getLiveState() ?? INITIAL_STATE);
    } catch (stopError) {
      setError(
        stopError instanceof Error
          ? stopError.message
          : "No se pudo detener la grabación.",
      );
    }
  }, []);

  const pauseRecording = useCallback(() => {
    controllerRef.current?.pause();
  }, []);

  const resumeRecording = useCallback(() => {
    controllerRef.current?.resume();
  }, []);

  const clearSections = useCallback(() => {
    setSections((current) => {
      for (const section of current) {
        URL.revokeObjectURL(section.url);
      }
      return [];
    });
    setSessionAudio((current) => {
      if (current) {
        URL.revokeObjectURL(current.url);
      }
      return null;
    });
    setLiveState(INITIAL_STATE);
  }, []);

  return {
    liveState,
    sections,
    sessionAudio,
    error,
    startRecording,
    stopRecording,
    pauseRecording,
    resumeRecording,
    clearSections,
  };
}
