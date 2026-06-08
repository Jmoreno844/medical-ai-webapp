import { type ChangeEvent, useEffect, useRef, useState } from "react";
import axios from "axios";
import { Button } from "@/commons/components/ui/button";
import { Card } from "@/commons/components/ui/card";
import { Input } from "@/commons/components/ui/input";
import { Badge } from "@/commons/components/ui/badge";
import { Separator } from "@/commons/components/ui/separator";
import axiosInstance from "@/commons/utils/axiosInstance";
import {
  AudioRecorderController,
  type CompletedSessionAudio,
  type LiveRecordingState,
  type RecordedSection,
} from "@/audio/recording/AudioRecorderController";
import {
  buildAudioSectionMetadataFromFrontendCut,
  type FrontendAudioProcessingTimings,
  prepareRecordedSectionArtifacts,
} from "@/audio/recording/postRecordingAudioPipeline";
import {
  buildRetainedIntervals,
  detectRemovableSilences,
  mergeSpeechIntervals,
} from "@/audio/segmentation/speechIntervals";
import type { SpeechInterval } from "@/audio/segmentation/types";
import { analyzeUploadedAudioWithSilero } from "@/audio/vad/analyzeUploadedAudioWithSilero";
import { getStoredMicrophoneDeviceId } from "@/features/encuentroHeader/hooks/audio/useMicrophoneDevices";
import { createChildLogger } from "@/lib/logger";
import {
  clearDebugSections,
  type DebugCutMetadata,
  type DebugSectionRecord,
  type DebugTranscriptResult,
  listDebugSections,
  saveDebugSection,
  updateDebugSection,
} from "./debugSectionStore";
import {
  AudioLines,
  Copy,
  Download,
  Loader2,
  Mic,
  Square,
  Upload,
  WandSparkles,
} from "lucide-react";

const logger = createChildLogger("DebugTranscription");

type ProviderKey = "gemini" | "workerVad";

type SectionView = DebugSectionRecord & {
  url: string;
};

type BackendDebugPayload = {
  success: boolean;
  mode?: "transcribe" | "vad_only";
  provider: string;
  model: string;
  transcript: string;
  content_type: string;
  vad_decision: string;
  vad_speech_ms: number;
  vad_speech_ratio: number;
  vad_error_code?: string | null;
  frontend_cut: {
    section_duration_ms: number;
    speech_duration_ms: number;
    speech_frame_count: number;
    has_detected_speech: boolean;
    cut_reason: string;
    overlap_ms: number;
    speech_intervals: Array<{ start_ms: number; end_ms: number }>;
    removable_silences: Array<{ start_ms: number; end_ms: number }>;
    retained_intervals: Array<{ start_ms: number; end_ms: number }>;
  };
  worker_input: {
    input_byte_size: number;
    decoded_sample_count: number;
    decoded_duration_ms: number;
    sample_rate_hz: number;
    trimmed_audio_byte_size: number;
  };
  worker_cut: {
    original_duration_ms: number;
    retained_duration_ms: number;
    speech_duration_ms: number;
    speech_ratio: number;
    retained_intervals: Array<{ start_ms: number; end_ms: number }>;
    removable_silences: Array<{ start_ms: number; end_ms: number }>;
    speech_intervals: Array<{ start_ms: number; end_ms: number }>;
    trim_applied: boolean;
  };
  comparison: {
    original_duration_ms: number;
    frontend_retained_duration_ms: number;
    worker_retained_duration_ms: number;
    retained_duration_delta_ms: number;
    frontend_removed_silence_ms: number;
    worker_removed_silence_ms: number;
    silence_removed_delta_ms: number;
  };
};

type AbsoluteInterval = SpeechInterval & {
  sectionId: string;
  sectionIndex: number;
};

const INITIAL_LIVE_STATE: LiveRecordingState = {
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

const formatMs = (value: number): string => {
  const totalSeconds = Math.max(0, Math.round(value / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds
    .toString()
    .padStart(2, "0")}`;
};

const toDebugCutFromRecordedSection = (
  section: RecordedSection,
): DebugCutMetadata => ({
  sectionDurationMs: section.metadata.wallClockDurationMs,
  speechDurationMs: section.metadata.speechDurationMs,
  speechFrameCount: Math.max(1, section.metadata.speechIntervals.length),
  hasDetectedSpeech: section.metadata.speechDurationMs > 0,
  cutReason: section.metadata.cutReason,
  overlapMs: section.metadata.overlapBeforeMs,
  speechIntervals: section.metadata.speechIntervals,
  removableSilences: section.metadata.removableSilences,
  retainedIntervals: buildRetainedIntervals(
    section.metadata.removableSilences,
    section.metadata.wallClockDurationMs,
  ),
});

const mapRecordedSectionToDebugRecord = (
  section: RecordedSection,
  blobDurationMs?: number,
): DebugSectionRecord => ({
  id: section.metadata.sectionId,
  blob: section.blob,
  startMs: Math.round(section.startTimeMs),
  endMs: Math.round(section.endTimeMs),
  durationMs: Math.round(section.endTimeMs - section.startTimeMs),
  blobDurationMs,
  mimeType: section.metadata.audioMimeType,
  frontendCut: toDebugCutFromRecordedSection(section),
  transcripts: {},
  status: "recorded",
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
});

const mapBackendPayloadToTranscriptResult = (
  payload: BackendDebugPayload,
  responseTimeMs: number,
): DebugTranscriptResult => ({
  mode: payload.mode ?? "transcribe",
  provider: payload.provider,
  model: payload.model,
  transcript: payload.transcript,
  contentType: payload.content_type,
  responseTimeMs,
  vadDecision: payload.vad_decision,
  vadSpeechMs: payload.vad_speech_ms,
  vadSpeechRatio: payload.vad_speech_ratio,
  vadErrorCode: payload.vad_error_code,
  frontendCut: {
    sectionDurationMs: payload.frontend_cut.section_duration_ms,
    speechDurationMs: payload.frontend_cut.speech_duration_ms,
    speechFrameCount: payload.frontend_cut.speech_frame_count,
    hasDetectedSpeech: payload.frontend_cut.has_detected_speech,
    cutReason: payload.frontend_cut.cut_reason as DebugCutMetadata["cutReason"],
    overlapMs: payload.frontend_cut.overlap_ms,
    speechIntervals: payload.frontend_cut.speech_intervals.map((interval) => ({
      startMs: interval.start_ms,
      endMs: interval.end_ms,
    })),
    removableSilences: payload.frontend_cut.removable_silences.map(
      (interval) => ({
        startMs: interval.start_ms,
        endMs: interval.end_ms,
      }),
    ),
    retainedIntervals: payload.frontend_cut.retained_intervals.map(
      (interval) => ({
        startMs: interval.start_ms,
        endMs: interval.end_ms,
      }),
    ),
  },
  workerInput: {
    inputByteSize: payload.worker_input.input_byte_size,
    decodedSampleCount: payload.worker_input.decoded_sample_count,
    decodedDurationMs: payload.worker_input.decoded_duration_ms,
    sampleRateHz: payload.worker_input.sample_rate_hz,
    trimmedAudioByteSize: payload.worker_input.trimmed_audio_byte_size,
  },
  workerCut: {
    originalDurationMs: payload.worker_cut.original_duration_ms,
    retainedDurationMs: payload.worker_cut.retained_duration_ms,
    speechDurationMs: payload.worker_cut.speech_duration_ms,
    speechRatio: payload.worker_cut.speech_ratio,
    retainedIntervals: payload.worker_cut.retained_intervals.map(
      (interval) => ({
        startMs: interval.start_ms,
        endMs: interval.end_ms,
      }),
    ),
    removableSilences: payload.worker_cut.removable_silences.map(
      (interval) => ({
        startMs: interval.start_ms,
        endMs: interval.end_ms,
      }),
    ),
    speechIntervals: payload.worker_cut.speech_intervals.map((interval) => ({
      startMs: interval.start_ms,
      endMs: interval.end_ms,
    })),
    trimApplied: payload.worker_cut.trim_applied,
  },
  comparison: {
    originalDurationMs: payload.comparison.original_duration_ms,
    frontendRetainedDurationMs:
      payload.comparison.frontend_retained_duration_ms,
    workerRetainedDurationMs: payload.comparison.worker_retained_duration_ms,
    retainedDurationDeltaMs: payload.comparison.retained_duration_delta_ms,
    frontendRemovedSilenceMs: payload.comparison.frontend_removed_silence_ms,
    workerRemovedSilenceMs: payload.comparison.worker_removed_silence_ms,
    silenceRemovedDeltaMs: payload.comparison.silence_removed_delta_ms,
  },
});

const toIntegerInterval = (interval: SpeechInterval) => ({
  start_ms: Math.max(0, Math.round(interval.startMs)),
  end_ms: Math.max(0, Math.round(interval.endMs)),
});

const serializeFrontendCut = (cut: DebugCutMetadata) => ({
  section_duration_ms: Math.max(0, Math.round(cut.sectionDurationMs)),
  speech_duration_ms: Math.max(0, Math.round(cut.speechDurationMs)),
  speech_frame_count: cut.speechFrameCount,
  has_detected_speech: cut.hasDetectedSpeech,
  cut_reason: cut.cutReason,
  overlap_ms: Math.max(0, Math.round(cut.overlapMs)),
  speech_intervals: cut.speechIntervals.map(toIntegerInterval),
  removable_silences: cut.removableSilences.map(toIntegerInterval),
  retained_intervals: cut.retainedIntervals.map(toIntegerInterval),
});

const toAbsoluteIntervals = (
  sections: SectionView[],
  picker: (section: SectionView) => SpeechInterval[],
): AbsoluteInterval[] =>
  sections.flatMap((section, index) =>
    picker(section).map((interval) => ({
      startMs: section.startMs + interval.startMs,
      endMs: section.startMs + interval.endMs,
      sectionId: section.id,
      sectionIndex: index,
    })),
  );

const getSectionVoiceSignalLabel = (section: SectionView) => {
  const ratio =
    section.durationMs > 0
      ? section.frontendCut.speechDurationMs / section.durationMs
      : 0;
  if (!section.frontendCut.hasDetectedSpeech) {
    return { label: "Frontend sin voz", tone: "outline" as const };
  }
  if (ratio >= 0.6) {
    return { label: "Frontend voz alta", tone: "default" as const };
  }
  if (ratio >= 0.25) {
    return { label: "Frontend voz media", tone: "secondary" as const };
  }
  return { label: "Frontend voz baja", tone: "outline" as const };
};

const formatBytes = (value: number): string => {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
};

const formatProcessingMs = (value: number): string => `${Math.max(0, Math.round(value))} ms`;

const getSafeWorkerInput = (result: DebugTranscriptResult) => ({
  inputByteSize: result.workerInput?.inputByteSize ?? 0,
  decodedSampleCount: result.workerInput?.decodedSampleCount ?? 0,
  decodedDurationMs:
    result.workerInput?.decodedDurationMs ??
    result.workerCut.originalDurationMs,
  sampleRateHz: result.workerInput?.sampleRateHz ?? 16000,
  trimmedAudioByteSize: result.workerInput?.trimmedAudioByteSize ?? 0,
});

export default function DebugTranscriptionPage() {
  const [sections, setSections] = useState<SectionView[]>([]);
  const [fullAudio, setFullAudio] = useState<CompletedSessionAudio | null>(
    null,
  );
  const [liveState, setLiveState] =
    useState<LiveRecordingState>(INITIAL_LIVE_STATE);
  const [error, setError] = useState<string | null>(null);
  const [geminiModel, setGeminiModel] = useState("gemini-2.5-flash");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [expandedDebugKeys, setExpandedDebugKeys] = useState<string[]>([]);
  const [frontendPreviewUrls, setFrontendPreviewUrls] = useState<
    Record<string, string>
  >({});
  const [frontendProcessingTimings, setFrontendProcessingTimings] = useState<
    Record<string, FrontendAudioProcessingTimings>
  >({});
  const [workerPreviewUrls, setWorkerPreviewUrls] = useState<
    Record<string, string>
  >({});

  const controllerRef = useRef<AudioRecorderController | null>(null);
  const sectionsRef = useRef<SectionView[]>([]);
  const fullAudioRef = useRef<CompletedSessionAudio | null>(null);

  const setSectionViews = (
    updater: (current: SectionView[]) => SectionView[],
  ) => {
    setSections((current) => {
      const next = updater(current);
      sectionsRef.current = next;
      return next;
    });
  };

  useEffect(() => {
    const controller = new AudioRecorderController();
    controllerRef.current = controller;

    const unsubscribeState = controller.onStateChange((state) => {
      setLiveState(state);
    });
    const unsubscribeSections = controller.onSectionRecorded(
      (recordedSection) => {
        const record = mapRecordedSectionToDebugRecord(recordedSection);
        void saveDebugSection(record);
        setSectionViews((current) => [
          ...current,
          {
            ...record,
            url: recordedSection.url,
          },
        ]);
        void (async () => {
          const blobDurationMs = await getAudioDurationMs(recordedSection.url);
          await updateDebugSection(record.id, { blobDurationMs });
          setSectionViews((current) =>
            current.map((item) =>
              item.id === record.id ? { ...item, blobDurationMs } : item,
            ),
          );
        })();
      },
    );
    const unsubscribeSessionAudio = controller.onSessionAudioReady((audio) => {
      setFullAudio((current) => {
        if (current) {
          URL.revokeObjectURL(current.url);
        }
        fullAudioRef.current = audio;
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

  useEffect(() => {
    void (async () => {
      const storedSections = await listDebugSections();
      const hydrated = await Promise.all(
        storedSections.map(async (section) => {
          const url = URL.createObjectURL(section.blob);
          const blobDurationMs =
            section.blobDurationMs ?? (await getAudioDurationMs(url));
          if (section.blobDurationMs == null) {
            await updateDebugSection(section.id, { blobDurationMs });
          }
          return {
            ...section,
            blobDurationMs,
            url,
          };
        }),
      );
      sectionsRef.current = hydrated;
      setSections(hydrated);
    })();
  }, []);

  useEffect(() => {
    return () => {
      for (const section of sectionsRef.current) {
        URL.revokeObjectURL(section.url);
      }
      for (const previewUrl of Object.values(frontendPreviewUrls)) {
        URL.revokeObjectURL(previewUrl);
      }
      for (const previewUrl of Object.values(workerPreviewUrls)) {
        URL.revokeObjectURL(previewUrl);
      }
      if (fullAudioRef.current) {
        URL.revokeObjectURL(fullAudioRef.current.url);
      }
    };
  }, [frontendPreviewUrls, workerPreviewUrls]);

  const getAudioDurationMs = (url: string): Promise<number> =>
    new Promise((resolve) => {
      const audio = new Audio();
      audio.preload = "metadata";
      audio.onloadedmetadata = () => {
        resolve(Number.isFinite(audio.duration) ? audio.duration * 1000 : 0);
      };
      audio.onerror = () => resolve(0);
      audio.src = url;
    });

  const startRecording = async () => {
    setError(null);
    try {
      await controllerRef.current?.start({
        preferredDeviceId: getStoredMicrophoneDeviceId(),
        collectFullSessionAudio: true,
      });
    } catch (recordingError) {
      logger.error(
        "[DebugTranscription] startRecording failed",
        recordingError,
      );
      setError("No se pudo iniciar la grabacion.");
    }
  };

  const stopRecording = () => {
    setError(null);
    void controllerRef.current?.stop();
  };

  const addUploadedAudio = async (file: File) => {
    const mimeType = file.type || "audio/webm";
    const sectionUrl = URL.createObjectURL(file);
    const probedDurationMs = await getAudioDurationMs(sectionUrl);
    let frontendCut: DebugCutMetadata = {
      sectionDurationMs: probedDurationMs,
      speechDurationMs: 0,
      speechFrameCount: 0,
      hasDetectedSpeech: false,
      cutReason: "uploaded_audio",
      overlapMs: 0,
      speechIntervals: [],
      removableSilences: [],
      retainedIntervals: [{ startMs: 0, endMs: probedDurationMs }],
    };

    try {
      const analysis = await analyzeUploadedAudioWithSilero(file);
      frontendCut = {
        sectionDurationMs: analysis.sectionDurationMs,
        speechDurationMs: analysis.speechDurationMs,
        speechFrameCount: analysis.speechFrameCount,
        hasDetectedSpeech: analysis.hasDetectedSpeech,
        cutReason: "uploaded_audio",
        overlapMs: 0,
        speechIntervals: analysis.speechIntervals,
        removableSilences: analysis.removableSilences,
        retainedIntervals: analysis.retainedIntervals,
      };
    } catch (analysisError) {
      logger.error("[DebugTranscription] uploaded audio frontend analysis failed", analysisError);
      setError(
        "No se pudo analizar el audio subido con el VAD de frontend. Puedes seguir usando Silero worker.",
      );
    }

    const durationMs = frontendCut.sectionDurationMs || probedDurationMs;

    const record: DebugSectionRecord = {
      id: crypto.randomUUID(),
      blob: file,
      startMs: 0,
      endMs: durationMs,
      durationMs,
      blobDurationMs: durationMs,
      mimeType,
      frontendCut,
      transcripts: {},
      status: "recorded",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    await saveDebugSection(record);
    setSectionViews((current) => [...current, { ...record, url: sectionUrl }]);
    setFullAudio((current) => {
      if (current) {
        URL.revokeObjectURL(current.url);
      }
      const uploaded = {
        blob: file,
        url: URL.createObjectURL(file),
        durationMs,
        mimeType,
      };
      fullAudioRef.current = uploaded;
      return uploaded;
    });
  };

  const handleAudioUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError(null);
    void addUploadedAudio(file).catch((uploadError) => {
      logger.error("[DebugTranscription] addUploadedAudio failed", uploadError);
      setError("No se pudo cargar el audio.");
    });
  };

  const clearSections = () => {
    for (const section of sectionsRef.current) {
      URL.revokeObjectURL(section.url);
    }
    setFrontendPreviewUrls((current) => {
      for (const previewUrl of Object.values(current)) {
        URL.revokeObjectURL(previewUrl);
      }
      return {};
    });
    setFrontendProcessingTimings(() => ({}));
    setWorkerPreviewUrls((current) => {
      for (const previewUrl of Object.values(current)) {
        URL.revokeObjectURL(previewUrl);
      }
      return {};
    });
    setSectionViews(() => []);
    setFullAudio((current) => {
      if (current) {
        URL.revokeObjectURL(current.url);
      }
      fullAudioRef.current = null;
      return null;
    });
    void clearDebugSections();
  };

  const previewFrontendTrimmedAudio = async (section: SectionView) => {
    setBusyKey(`${section.id}:frontendPreview`);
    setError(null);

    try {
      const metadata = buildAudioSectionMetadataFromFrontendCut({
        sectionId: section.id,
        sequence: section.startMs,
        audioMimeType: section.mimeType,
        cut: section.frontendCut,
      });
      const preparedArtifacts = await prepareRecordedSectionArtifacts(
        section.blob,
        metadata,
      );
      const previewUrl = URL.createObjectURL(preparedArtifacts.clippedBlob);
      setFrontendProcessingTimings((current) => ({
        ...current,
        [section.id]: preparedArtifacts.processingTimingsMs,
      }));
      setFrontendPreviewUrls((current) => {
        const previousUrl = current[section.id];
        if (previousUrl) {
          URL.revokeObjectURL(previousUrl);
        }
        return {
          ...current,
          [section.id]: previewUrl,
        };
      });
    } catch (previewError) {
      logger.error(
        "[DebugTranscription] previewFrontendTrimmedAudio failed",
        previewError,
      );
      setError("No se pudo generar el preview del corte frontend.");
    } finally {
      setBusyKey(null);
    }
  };

  const previewWorkerTrimmedAudio = async (section: SectionView) => {
    setBusyKey(`${section.id}:workerPreview`);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", section.blob, `${section.id}.webm`);
      formData.append("section_id", section.id);
      formData.append("content_type", section.mimeType);

      const response = await axiosInstance.post(
        "/api/v1/transcription/debug/sections/trimmed-audio",
        formData,
        { responseType: "blob" },
      );
      const previewBlob = response.data as Blob;
      const previewUrl = URL.createObjectURL(previewBlob);
      setWorkerPreviewUrls((current) => {
        const previousUrl = current[section.id];
        if (previousUrl) {
          URL.revokeObjectURL(previousUrl);
        }
        return {
          ...current,
          [section.id]: previewUrl,
        };
      });
    } catch (previewError) {
      logger.error(
        "[DebugTranscription] previewWorkerTrimmedAudio failed",
        previewError,
      );
      const backendDetail = axios.isAxiosError(previewError)
        ? ((previewError.response?.data as
            | { detail?: string | string[] }
            | undefined)?.detail ?? previewError.message)
        : "Error desconocido";
      setError(
        `Fallo el preview del audio recortado por worker: ${
          Array.isArray(backendDetail)
            ? backendDetail.join(", ")
            : backendDetail
        }`,
      );
    } finally {
      setBusyKey(null);
    }
  };

  const transcribeSection = async (
    section: SectionView,
    providerKey: ProviderKey,
  ) => {
    const isVadOnly = providerKey === "workerVad";
    const model = isVadOnly ? "silero_vad_only" : geminiModel;

    setBusyKey(`${section.id}:${providerKey}`);
    setError(null);
    await updateDebugSection(section.id, { status: "processing" });
    setSectionViews((current) =>
      current.map((item) =>
        item.id === section.id ? { ...item, status: "processing" } : item,
      ),
    );

    try {
      const formData = new FormData();
      formData.append("file", section.blob, `${section.id}.webm`);
      formData.append("mode", isVadOnly ? "vad_only" : "transcribe");
      formData.append(
        "provider",
        "google_genai",
      );
      formData.append("model", model);
      formData.append("section_id", section.id);
      formData.append("start_time_ms", String(section.startMs));
      formData.append("end_time_ms", String(section.endMs));
      formData.append("overlap_ms", String(section.frontendCut.overlapMs));
      formData.append("content_type", section.mimeType);
      formData.append(
        "frontend_cut_json",
        JSON.stringify(serializeFrontendCut(section.frontendCut)),
      );

      const requestStartedAt = performance.now();
      const response = await axiosInstance.post(
        "/api/v1/transcription/debug/sections",
        formData,
      );
      const result = mapBackendPayloadToTranscriptResult(
        response.data as BackendDebugPayload,
        performance.now() - requestStartedAt,
      );
      const transcripts = {
        ...section.transcripts,
        [providerKey]: result,
      };
      await updateDebugSection(section.id, {
        transcripts,
        status: "processed",
      });
      setSectionViews((current) =>
        current.map((item) =>
          item.id === section.id
            ? { ...item, transcripts, status: "processed" }
            : item,
        ),
      );
    } catch (transcriptionError) {
      logger.error(
        "[DebugTranscription] transcribeSection failed",
        providerKey,
        transcriptionError,
      );
      await updateDebugSection(section.id, { status: "failed" });
      setSectionViews((current) =>
        current.map((item) =>
          item.id === section.id ? { ...item, status: "failed" } : item,
        ),
      );
      const backendDetail = axios.isAxiosError(transcriptionError)
        ? ((
            transcriptionError.response?.data as
              | { detail?: string | string[] }
              | undefined
          )?.detail ?? transcriptionError.message)
        : "Error desconocido";
      setError(
        providerKey === "workerVad"
          ? `Fallo el debug del worker Silero: ${Array.isArray(backendDetail) ? backendDetail.join(", ") : backendDetail}`
          : `Fallo la transcripcion con Gemini: ${Array.isArray(backendDetail) ? backendDetail.join(", ") : backendDetail}`,
      );
    } finally {
      setBusyKey(null);
    }
  };

  const transcribeAll = async (providerKey: ProviderKey) => {
    for (const section of sectionsRef.current) {
      await transcribeSection(section, providerKey);
    }
  };

  const copyText = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
    } catch (copyError) {
      logger.error("[DebugTranscription] copy failed", copyError);
      setError("No se pudo copiar el texto.");
    }
  };

  const renderTranscriptSurface = (value: string) => (
    <div className="min-h-[180px] whitespace-pre-wrap break-words rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-800">
      {value || (
        <span className="text-slate-400">Sin transcripcion todavia.</span>
      )}
    </div>
  );

  const formatIntervalLabel = (interval: SpeechInterval) =>
    `${formatMs(interval.startMs)} - ${formatMs(interval.endMs)} (${formatMs(
      interval.endMs - interval.startMs,
    )})`;

  const renderIntervals = (
    title: string,
    intervals: SpeechInterval[],
    emptyLabel: string,
  ) => (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {title}
      </p>
      {intervals.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">{emptyLabel}</p>
      ) : (
        <div className="mt-2 space-y-1 text-sm text-slate-800">
          {intervals.map((interval, index) => (
            <div key={`${title}-${index}`}>{formatIntervalLabel(interval)}</div>
          ))}
        </div>
      )}
    </div>
  );

  const toggleExpandedDebug = (key: string) => {
    setExpandedDebugKeys((current) =>
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key],
    );
  };

  const renderDebugBreakdown = (
    providerLabel: string,
    result: DebugTranscriptResult | undefined,
    sectionDurationMs: number,
    blobDurationMs: number | undefined,
    isExpanded: boolean,
    toggleKey: string,
  ) => {
    if (!result) {
      return null;
    }

    const workerInput = getSafeWorkerInput(result);
    const workerDurationDeltaMs =
      sectionDurationMs - result.workerCut.originalDurationMs;
    const hasWorkerDurationMismatch = Math.abs(workerDurationDeltaMs) >= 1500;
    const blobDurationDeltaMs =
      (blobDurationMs ?? sectionDurationMs) - workerInput.decodedDurationMs;
    const hasBlobDurationMismatch = Math.abs(blobDurationDeltaMs) >= 1500;

    return (
      <div className="space-y-3 rounded-md border border-slate-200 bg-slate-50 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{providerLabel}</Badge>
            <Badge variant="outline">
              UI seccion: {formatMs(sectionDurationMs)}
            </Badge>
            {blobDurationMs != null ? (
              <Badge variant="outline">
                Blob navegador: {formatMs(blobDurationMs)}
              </Badge>
            ) : null}
            <Badge variant="outline">
              Worker analizo: {formatMs(result.workerCut.originalDurationMs)}
            </Badge>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => toggleExpandedDebug(toggleKey)}
          >
            {isExpanded
              ? "Ocultar debug"
              : "Ver debug frontend / backend / worker"}
          </Button>
        </div>

        {hasWorkerDurationMismatch ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            El worker analizo {formatMs(result.workerCut.originalDurationMs)} de
            una seccion que en la UI dura {formatMs(sectionDurationMs)}.
          </div>
        ) : null}

        {hasBlobDurationMismatch ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            El blob del navegador dura{" "}
            {formatMs(blobDurationMs ?? sectionDurationMs)}, pero el worker
            decodifico {formatMs(workerInput.decodedDurationMs)}.
          </div>
        ) : null}

        {isExpanded ? (
          <div className="grid gap-3 xl:grid-cols-3">
            <div className="space-y-3">
              <div className="rounded-md border border-slate-200 bg-white p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Frontend
                </p>
                <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-slate-800">
                  <span className="text-slate-500">Corte</span>
                  <span className="text-right">
                    {result.frontendCut.cutReason}
                  </span>
                  <span className="text-slate-500">Duracion total</span>
                  <span className="text-right">
                    {formatMs(result.frontendCut.sectionDurationMs)}
                  </span>
                  <span className="text-slate-500">Blob navegador</span>
                  <span className="text-right">
                    {blobDurationMs != null
                      ? formatMs(blobDurationMs)
                      : "Pendiente"}
                  </span>
                  <span className="text-slate-500">Voz detectada</span>
                  <span className="text-right">
                    {formatMs(result.frontendCut.speechDurationMs)}
                  </span>
                </div>
              </div>
              {renderIntervals(
                "Intervalos de voz frontend",
                result.frontendCut.speechIntervals,
                "No se registraron intervalos de voz en frontend.",
              )}
              {renderIntervals(
                "Silencios removibles frontend",
                result.frontendCut.removableSilences,
                "Ninguno detectado.",
              )}
            </div>

            <div className="space-y-3">
              <div className="rounded-md border border-slate-200 bg-white p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Backend bridge
                </p>
                <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-slate-800">
                  <span className="text-slate-500">Modo</span>
                  <span className="text-right">
                    {result.mode === "vad_only"
                      ? "Solo VAD worker"
                      : "Transcripcion"}
                  </span>
                  <span className="text-slate-500">Endpoint</span>
                  <span className="text-right font-mono text-xs">
                    /api/v1/transcription/debug/sections
                  </span>
                  <span className="text-slate-500">Provider</span>
                  <span className="text-right">{result.provider}</span>
                  <span className="text-slate-500">Modelo</span>
                  <span className="text-right">{result.model}</span>
                  <span className="text-slate-500">Bytes enviados</span>
                  <span className="text-right">
                    {formatBytes(workerInput.inputByteSize)}
                  </span>
                </div>
              </div>
              <div className="rounded-md border border-slate-200 bg-white p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Comparacion
                </p>
                <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-slate-800">
                  <span className="text-slate-500">Frontend retenido</span>
                  <span className="text-right">
                    {formatMs(result.comparison.frontendRetainedDurationMs)}
                  </span>
                  <span className="text-slate-500">Worker retenido</span>
                  <span className="text-right">
                    {formatMs(result.comparison.workerRetainedDurationMs)}
                  </span>
                  <span className="text-slate-500">Delta silencio</span>
                  <span className="text-right">
                    {result.comparison.silenceRemovedDeltaMs} ms
                  </span>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="rounded-md border border-slate-200 bg-white p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Worker
                </p>
                <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-slate-800">
                  <span className="text-slate-500">Duracion analizada</span>
                  <span className="text-right">
                    {formatMs(result.workerCut.originalDurationMs)}
                  </span>
                  <span className="text-slate-500">Duracion decodificada</span>
                  <span className="text-right">
                    {formatMs(workerInput.decodedDurationMs)}
                  </span>
                  <span className="text-slate-500">Duracion retenida</span>
                  <span className="text-right">
                    {formatMs(result.workerCut.retainedDurationMs)}
                  </span>
                  <span className="text-slate-500">Voz detectada</span>
                  <span className="text-right">
                    {formatMs(result.workerCut.speechDurationMs)}
                  </span>
                  <span className="text-slate-500">Muestras</span>
                  <span className="text-right">
                    {workerInput.decodedSampleCount.toLocaleString()}
                  </span>
                  <span className="text-slate-500">WAV recortado</span>
                  <span className="text-right">
                    {formatBytes(workerInput.trimmedAudioByteSize)}
                  </span>
                </div>
              </div>
              {renderIntervals(
                "Intervalos de voz worker",
                result.workerCut.speechIntervals,
                "No se registraron intervalos de voz en worker.",
              )}
              {renderIntervals(
                "Silencios removibles worker",
                result.workerCut.removableSilences,
                "Ninguno detectado.",
              )}
            </div>
          </div>
        ) : null}
      </div>
    );
  };

  const renderComparison = (result: DebugTranscriptResult | undefined) => {
    if (!result) return null;
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
        <div className="grid grid-cols-2 gap-2">
          <span className="text-slate-500">Frontend retenido</span>
          <span className="text-right font-medium">
            {formatMs(result.comparison.frontendRetainedDurationMs)}
          </span>
          <span className="text-slate-500">Worker retenido</span>
          <span className="text-right font-medium">
            {formatMs(result.comparison.workerRetainedDurationMs)}
          </span>
          <span className="text-slate-500">Silencio removido frontend</span>
          <span className="text-right font-medium">
            {result.comparison.frontendRemovedSilenceMs} ms
          </span>
          <span className="text-slate-500">Silencio removido worker</span>
          <span className="text-right font-medium">
            {result.comparison.workerRemovedSilenceMs} ms
          </span>
        </div>
      </div>
    );
  };

  const absoluteFrontendSpeech = toAbsoluteIntervals(
    sections,
    (section) => section.frontendCut.speechIntervals,
  );
  const timelineDurationMs =
    fullAudio?.durationMs ?? sections.at(-1)?.endMs ?? 0;
  const mergedAbsoluteFrontendSpeech = mergeSpeechIntervals(
    absoluteFrontendSpeech
      .map((interval) => ({
        startMs: Math.round(interval.startMs),
        endMs: Math.round(interval.endMs),
      }))
      .sort((left, right) => left.startMs - right.startMs),
  );
  const absoluteFrontendSilences = detectRemovableSilences(
    mergedAbsoluteFrontendSpeech,
    timelineDurationMs,
  );
  const totalFrontendSpeechMs = sections.reduce(
    (total, section) => total + section.frontendCut.speechDurationMs,
    0,
  );

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 py-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Debug de transcripcion
        </h1>
        <p className="max-w-3xl text-sm text-slate-600">
          Esta pagina usa el mismo motor de seccionado que grabacion y
          produccion: minimo 60 s de voz real antes del corte natural, cierre
          forzado cerca de 90 s de voz y silencios de 3 s solo como metadata.
        </p>
      </div>

      <Card className="grid gap-4 border border-slate-200 p-5 lg:grid-cols-[1.2fr_1fr]">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button
              onClick={liveState.isRecording ? stopRecording : startRecording}
            >
              {liveState.isRecording ? (
                <>
                  <Square className="mr-2 h-4 w-4" />
                  Detener
                </>
              ) : (
                <>
                  <Mic className="mr-2 h-4 w-4" />
                  Grabar
                </>
              )}
            </Button>
            <Button
              variant="outline"
              onClick={clearSections}
              disabled={liveState.isRecording}
            >
              Limpiar secciones
            </Button>
            <Badge variant={liveState.isRecording ? "secondary" : "outline"}>
              {liveState.isRecording ? "Grabando" : "En espera"}
            </Badge>
            <Badge variant="outline">
              {formatMs(liveState.wallClockDurationMs)}
            </Badge>
            <Badge variant="outline">
              Voz actual: {formatMs(liveState.speechDurationMs)}
            </Badge>
            <Badge variant="outline">
              Silencio actual: {Math.round(liveState.currentSilenceMs)} ms
            </Badge>
          </div>

          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          ) : null}

          <div className="max-w-md">
            <div className="space-y-2">
              <label className="text-sm font-medium">Modelo Gemini</label>
              <Input
                value={geminiModel}
                onChange={(event) => setGeminiModel(event.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <label
                htmlFor="debug-audio-upload"
                className={
                  liveState.isRecording ? "pointer-events-none opacity-50" : ""
                }
              >
                <Upload className="mr-2 h-4 w-4" />
                Subir audio
              </label>
            </Button>
            <input
              id="debug-audio-upload"
              type="file"
              accept="audio/*"
              className="hidden"
              disabled={liveState.isRecording}
              onChange={handleAudioUpload}
            />
            <Button
              variant="outline"
              onClick={() => void transcribeAll("workerVad")}
              disabled={sections.length === 0 || Boolean(busyKey)}
            >
              <AudioLines className="mr-2 h-4 w-4" />
              Silero worker
            </Button>
            <Button
              variant="outline"
              onClick={() => void transcribeAll("gemini")}
              disabled={sections.length === 0 || Boolean(busyKey)}
            >
              <WandSparkles className="mr-2 h-4 w-4" />
              Transcribir todo con Gemini
            </Button>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
          <p className="font-medium text-slate-900">Capas de debug</p>
          <div className="mt-2 space-y-2 text-sm">
            <div className="rounded-md border border-slate-200 bg-white px-3 py-2">
              <span className="font-medium">1. Frontend</span>: usa el mismo
              motor real de 60–90 s de voz.
            </div>
            <div className="rounded-md border border-slate-200 bg-white px-3 py-2">
              <span className="font-medium">2. Backend bridge</span>: reenvia la
              seccion a <code>/api/v1/transcription/debug/sections</code>.
            </div>
            <div className="rounded-md border border-slate-200 bg-white px-3 py-2">
              <span className="font-medium">3. Worker</span>: recalcula voz y
              silencios; luego transcribe solo si se lo pides.
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-600">
            Aqui ya no se usan cortes tempranos de 10–30 s. Si ves una seccion
            corta, debe venir de stop manual o fallback real, no de una politica
            paralela.
          </p>
        </div>
      </Card>

      {(fullAudio || sections.length > 0) && (
        <Card className="border border-slate-200 p-5">
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">
                  Audio general
                </h2>
                <p className="text-sm text-slate-600">
                  Primero se ve el audio completo y luego las secciones.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">
                  Timeline: {formatMs(timelineDurationMs)}
                </Badge>
                <Badge variant="outline">Secciones: {sections.length}</Badge>
                <Badge variant="outline">
                  Voz frontend: {formatMs(totalFrontendSpeechMs)}
                </Badge>
              </div>
            </div>

            {fullAudio ? (
              <div className="rounded-lg border border-slate-200 bg-white p-3">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">Grabacion completa</Badge>
                    <Badge variant="outline">
                      {formatMs(fullAudio.durationMs)}
                    </Badge>
                    <Badge variant="outline">{fullAudio.mimeType}</Badge>
                  </div>
                  <Button asChild size="sm" variant="outline">
                    <a href={fullAudio.url} download="debug-transcripcion.webm">
                      <Download className="mr-2 h-4 w-4" />
                      Descargar
                    </a>
                  </Button>
                </div>
                <audio controls src={fullAudio.url} className="h-10 w-full" />
              </div>
            ) : null}

            <div className="grid gap-4 lg:grid-cols-2">
              {renderIntervals(
                "Silencios candidatos en audio completo",
                absoluteFrontendSilences,
                "No hay silencios de 3 s o mas marcados por frontend.",
              )}
              {renderIntervals(
                "Voz detectada en audio completo",
                mergedAbsoluteFrontendSpeech,
                "No hay intervalos de voz marcados por frontend.",
              )}
            </div>
          </div>
        </Card>
      )}

      <div className="grid gap-4">
        {sections.map((section, index) => {
          const workerVadResult = section.transcripts.workerVad;
          const geminiResult = section.transcripts.gemini;
          const bestWorkerResult = workerVadResult ?? geminiResult;
          const frontendVoiceSignal = getSectionVoiceSignalLabel(section);
          const frontendPreviewUrl = frontendPreviewUrls[section.id];
          const frontendTimings = frontendProcessingTimings[section.id];
          const workerPreviewUrl = workerPreviewUrls[section.id];

          return (
            <Card key={section.id} className="border border-slate-200 p-5">
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge>{`Seccion ${index + 1}`}</Badge>
                    <Badge variant="outline">
                      {formatMs(section.startMs)} - {formatMs(section.endMs)}
                    </Badge>
                    <Badge variant="outline">
                      {formatMs(section.durationMs)}
                    </Badge>
                    <Badge variant="outline">{section.status}</Badge>
                    <Badge variant={frontendVoiceSignal.tone}>
                      {frontendVoiceSignal.label}
                    </Badge>
                    {bestWorkerResult ? (
                      <Badge variant="outline">
                        Worker Silero: {bestWorkerResult.vadDecision} ·{" "}
                        {(bestWorkerResult.vadSpeechRatio * 100).toFixed(0)}%
                      </Badge>
                    ) : (
                      <Badge variant="outline">Worker Silero: pendiente</Badge>
                    )}
                  </div>
                  <audio
                    controls
                    src={section.url}
                    className="h-10 w-full max-w-md"
                  />
                </div>

                <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                  Frontend: corta esta seccion por{" "}
                  <strong>{section.frontendCut.cutReason}</strong>, marca{" "}
                  {formatMs(section.frontendCut.speechDurationMs)} de voz y{" "}
                  {section.frontendCut.removableSilences.length} silencio(s)
                  candidato(s).
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    onClick={() => void previewFrontendTrimmedAudio(section)}
                    disabled={busyKey !== null}
                  >
                    {busyKey === `${section.id}:frontendPreview` ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <AudioLines className="mr-2 h-4 w-4" />
                    )}
                    Preview corte frontend
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => void transcribeSection(section, "workerVad")}
                    disabled={busyKey !== null}
                  >
                    {busyKey === `${section.id}:workerVad` ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <AudioLines className="mr-2 h-4 w-4" />
                    )}
                    Silero worker
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => void previewWorkerTrimmedAudio(section)}
                    disabled={busyKey !== null}
                  >
                    {busyKey === `${section.id}:workerPreview` ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <AudioLines className="mr-2 h-4 w-4" />
                    )}
                    Preview corte worker
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => void transcribeSection(section, "gemini")}
                    disabled={busyKey !== null}
                  >
                    {busyKey === `${section.id}:gemini` ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <WandSparkles className="mr-2 h-4 w-4" />
                    )}
                    Gemini
                  </Button>
                </div>

                {frontendPreviewUrl ? (
                  <div className="space-y-2 rounded-md border border-slate-200 bg-white p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">
                          Audio unido tras corte frontend
                        </span>
                        <Badge variant="secondary">Opus preview</Badge>
                      </div>
                      <Button asChild size="sm" variant="ghost">
                        <a
                          href={frontendPreviewUrl}
                          download={`${section.id}-frontend-trimmed.ogg`}
                        >
                          <Download className="mr-2 h-4 w-4" />
                          Descargar
                        </a>
                      </Button>
                    </div>
                    <p className="text-xs text-slate-500">
                      Este player reproduce los tramos retenidos por el corte
                      frontend usando el mismo pipeline local que produccion.
                    </p>
                    {frontendTimings ? (
                      <div className="grid grid-cols-2 gap-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                        <span className="text-slate-500">Decode</span>
                        <span className="text-right font-medium">
                          {formatProcessingMs(frontendTimings.decodeMs)}
                        </span>
                        <span className="text-slate-500">Encoder</span>
                        <span className="text-right font-medium">
                          {frontendTimings.encoderBackend}
                        </span>
                        <span className="text-slate-500">Normalizar / cortar</span>
                        <span className="text-right font-medium">
                          {formatProcessingMs(frontendTimings.normalizeAndCutMs)}
                        </span>
                        <span className="text-slate-500">Encode Opus</span>
                        <span className="text-right font-medium">
                          {formatProcessingMs(frontendTimings.encodeMs)}
                        </span>
                        <span className="text-slate-500">Total frontend</span>
                        <span className="text-right font-medium">
                          {formatProcessingMs(frontendTimings.totalMs)}
                        </span>
                        {frontendTimings.encoderFallbackReason ? (
                          <>
                            <span className="text-slate-500">Fallback</span>
                            <span className="text-right font-medium">
                              {frontendTimings.encoderFallbackReason}
                            </span>
                          </>
                        ) : null}
                      </div>
                    ) : null}
                    <audio
                      controls
                      src={frontendPreviewUrl}
                      className="h-10 w-full"
                    />
                  </div>
                ) : null}

                {workerPreviewUrl ? (
                  <div className="space-y-2 rounded-md border border-slate-200 bg-white p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">
                          Audio unido tras corte worker
                        </span>
                        <Badge variant="secondary">WAV preview</Badge>
                      </div>
                      <Button asChild size="sm" variant="ghost">
                        <a
                          href={workerPreviewUrl}
                          download={`${section.id}-worker-trimmed.wav`}
                        >
                          <Download className="mr-2 h-4 w-4" />
                          Descargar
                        </a>
                      </Button>
                    </div>
                    <p className="text-xs text-slate-500">
                      Este player reproduce los tramos retenidos por Silero
                      worker ya unidos despues de remover los silencios largos.
                    </p>
                    <audio
                      controls
                      src={workerPreviewUrl}
                      className="h-10 w-full"
                    />
                  </div>
                ) : null}

                {workerVadResult ? (
                  <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">
                          Silero worker
                        </span>
                        <Badge variant="secondary">Solo VAD</Badge>
                      </div>
                      <Badge variant="outline">
                        voz {workerVadResult.vadSpeechMs} ms · ratio{" "}
                        {workerVadResult.vadSpeechRatio.toFixed(3)}
                      </Badge>
                    </div>
                    {renderComparison(workerVadResult)}
                    {renderDebugBreakdown(
                      "Silero worker",
                      workerVadResult,
                      section.durationMs,
                      section.blobDurationMs,
                      expandedDebugKeys.includes(`${section.id}:workerVad`),
                      `${section.id}:workerVad`,
                    )}
                  </div>
                ) : null}

                <div className="space-y-2">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">Gemini</span>
                        {geminiResult ? (
                          <Badge variant="secondary">
                            {geminiResult.model}
                          </Badge>
                        ) : null}
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          void copyText(geminiResult?.transcript || "")
                        }
                        disabled={!geminiResult?.transcript}
                      >
                        <Copy className="mr-2 h-4 w-4" />
                        Copiar
                      </Button>
                    </div>
                    {renderTranscriptSurface(geminiResult?.transcript || "")}
                    {geminiResult ? (
                      <>
                        <p className="text-xs text-slate-500">
                          VAD: {geminiResult.vadDecision} | voz{" "}
                          {geminiResult.vadSpeechMs} ms | ratio{" "}
                          {geminiResult.vadSpeechRatio.toFixed(3)}
                        </p>
                        {renderComparison(geminiResult)}
                        {renderDebugBreakdown(
                          "Gemini",
                          geminiResult,
                          section.durationMs,
                          section.blobDurationMs,
                          expandedDebugKeys.includes(`${section.id}:gemini`),
                          `${section.id}:gemini`,
                        )}
                      </>
                    ) : null}
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {sections.length === 0 ? (
        <>
          <Separator />
          <p className="text-sm text-slate-500">
            Graba una muestra o sube audio. Las secciones grabadas ahora usan el
            mismo criterio de produccion.
          </p>
        </>
      ) : null}
    </div>
  );
}
