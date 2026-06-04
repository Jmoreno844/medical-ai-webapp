import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { Button } from "@/commons/components/ui/button";
import { Card } from "@/commons/components/ui/card";
import { Input } from "@/commons/components/ui/input";
import { Badge } from "@/commons/components/ui/badge";
import { Separator } from "@/commons/components/ui/separator";
import { createChildLogger } from "@/lib/logger";
import { getBestSupportedAudioType } from "@/features/encuentroHeader/hooks/audio/utils";
import {
  AUDIO_SEGMENTATION_CONFIG,
  detectVoiceActivity,
  getNaturalPauseThresholdMs,
  shouldFlushOnNaturalPause,
  shouldForceSectionCut,
  shouldUploadSectionForTranscription,
  VAD_ANALYSER_FFT_SIZE,
} from "@/features/encuentroHeader/hooks/audio/vad";
import {
  Copy,
  Download,
  Loader2,
  Mic,
  Square,
  Upload,
  WandSparkles,
  AudioLines,
} from "lucide-react";

const logger = createChildLogger("DebugTranscription");
const WORKER_URL =
  import.meta.env.VITE_TRANSCRIPTION_WORKER_URL || "http://localhost:8091";

type ProviderKey = "gemini" | "openai";

type RecorderSection = {
  id: string;
  recorder: MediaRecorder;
  chunks: Blob[];
  startedAtMs: number;
  overlapMs: number;
  hasDetectedSpeech: boolean;
  speechFrameCount: number;
};

type TranscriptResult = {
  transcript: string;
  vadDecision: string;
  vadSpeechMs: number;
  vadSpeechRatio: number;
  model: string;
  contentType: string;
  responseTimeMs: number;
};

type SectionItem = {
  id: string;
  blob: Blob;
  url: string;
  startMs: number;
  endMs: number;
  durationMs: number;
  mimeType: string;
  transcripts: Partial<Record<ProviderKey, TranscriptResult>>;
};

type FullAudioItem = {
  blob: Blob;
  url: string;
  durationMs: number;
  mimeType: string;
  name: string;
  source: "recording" | "upload";
};

type SectionTranscriptionPayload = {
  success: boolean;
  provider: string;
  model: string;
  transcript: string;
  content_type: string;
  vad_decision: string;
  vad_speech_ms: number;
  vad_speech_ratio: number;
};

type VadDebugState = {
  sectionDurationMs: number;
  stableSilenceMs: number;
  naturalPauseThresholdMs: number;
  rms: number;
  peak: number;
  isSpeech: boolean;
};

const formatMs = (value: number): string => {
  const totalSeconds = Math.max(0, Math.round(value / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds
    .toString()
    .padStart(2, "0")}`;
};

const makeSectionId = (): string =>
  `section_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

export default function DebugTranscriptionPage() {
  const [sections, setSections] = useState<SectionItem[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [geminiModel, setGeminiModel] = useState("gemini-2.5-flash");
  const [openaiModel, setOpenaiModel] = useState("gpt-4o-mini-transcribe");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [vadDebug, setVadDebug] = useState<VadDebugState | null>(null);
  const [fullAudio, setFullAudio] = useState<FullAudioItem | null>(null);

  const isRecordingRef = useRef(false);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const fullRecorderRef = useRef<MediaRecorder | null>(null);
  const fullRecordingChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const vadBufferRef = useRef<Float32Array | null>(null);
  const vadIntervalRef = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);
  const mimeTypeRef = useRef("audio/webm");
  const sectionsRef = useRef<SectionItem[]>([]);
  const fullAudioRef = useRef<FullAudioItem | null>(null);
  const recordingStartedAtRef = useRef(0);
  const activeSectionRef = useRef<RecorderSection | null>(null);
  const retiringSectionRef = useRef<RecorderSection | null>(null);
  const forcedSplitInFlightRef = useRef(false);
  const overlapTimerRef = useRef<number | null>(null);
  const sectionBoundaryTimerRef = useRef<number | null>(null);
  const lastSpeechAtMsRef = useRef(0);

  const getRecordingElapsedMs = () =>
    Date.now() - recordingStartedAtRef.current;

  const replaceFullAudio = (nextAudio: FullAudioItem | null) => {
    setFullAudio((currentAudio) => {
      if (currentAudio) {
        URL.revokeObjectURL(currentAudio.url);
      }
      return nextAudio;
    });
  };

  const clearTimers = () => {
    if (vadIntervalRef.current !== null) {
      window.clearInterval(vadIntervalRef.current);
      vadIntervalRef.current = null;
    }
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (overlapTimerRef.current !== null) {
      window.clearTimeout(overlapTimerRef.current);
      overlapTimerRef.current = null;
    }
    if (sectionBoundaryTimerRef.current !== null) {
      window.clearTimeout(sectionBoundaryTimerRef.current);
      sectionBoundaryTimerRef.current = null;
    }
  };

  const cleanupMedia = () => {
    clearTimers();
    analyserRef.current = null;
    vadBufferRef.current = null;
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }
    recorderRef.current = null;
    fullRecorderRef.current = null;
    fullRecordingChunksRef.current = [];
    activeSectionRef.current = null;
    retiringSectionRef.current = null;
    forcedSplitInFlightRef.current = false;
    setVadDebug(null);
  };

  useEffect(() => {
    sectionsRef.current = sections;
  }, [sections]);

  useEffect(() => {
    fullAudioRef.current = fullAudio;
  }, [fullAudio]);

  useEffect(() => {
    return () => {
      cleanupMedia();
      for (const section of sectionsRef.current) {
        URL.revokeObjectURL(section.url);
      }
      if (fullAudioRef.current) {
        URL.revokeObjectURL(fullAudioRef.current.url);
      }
    };
  }, []);

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

  const createFullSessionRecorder = (stream: MediaStream) => {
    const recorder = new MediaRecorder(stream, {
      mimeType: mimeTypeRef.current,
      audioBitsPerSecond: 24000,
    });
    fullRecordingChunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        fullRecordingChunksRef.current.push(event.data);
      }
    };
    recorder.start();
    fullRecorderRef.current = recorder;
  };

  const stopFullSessionRecorder = async (): Promise<Blob | null> => {
    const recorder = fullRecorderRef.current;
    if (!recorder) return null;

    if (recorder.state === "inactive") {
      return fullRecordingChunksRef.current.length > 0
        ? new Blob(fullRecordingChunksRef.current, {
            type: recorder.mimeType || mimeTypeRef.current,
          })
        : null;
    }

    return new Promise((resolve) => {
      const mimeType = recorder.mimeType || mimeTypeRef.current;
      let settled = false;
      let timeoutId: number | null = null;

      const settle = () => {
        if (settled) return;
        settled = true;
        if (timeoutId !== null) {
          window.clearTimeout(timeoutId);
        }
        const blob =
          fullRecordingChunksRef.current.length > 0
            ? new Blob(fullRecordingChunksRef.current, { type: mimeType })
            : null;
        resolve(blob);
      };

      recorder.onstop = settle;
      timeoutId = window.setTimeout(() => {
        logger.warn(
          "[DebugTranscription] Full MediaRecorder stop timed out; finalizing available chunks",
        );
        settle();
      }, 2500);

      try {
        if (recorder.state !== "inactive") {
          recorder.requestData();
        }
        recorder.stop();
      } catch (error) {
        logger.error("[DebugTranscription] stopFullSessionRecorder failed", error);
        settle();
      }
    });
  };

  const createSectionRecorder = (
    stream: MediaStream,
    overlapMs: number,
  ): RecorderSection => {
    const recorder = new MediaRecorder(stream, {
      mimeType: mimeTypeRef.current,
      audioBitsPerSecond: 24000,
    });
    const section: RecorderSection = {
      id: makeSectionId(),
      recorder,
      chunks: [],
      startedAtMs: getRecordingElapsedMs(),
      overlapMs,
      hasDetectedSpeech: false,
      speechFrameCount: 0,
    };
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        section.chunks.push(event.data);
      }
    };
    recorder.start();
    return section;
  };

  const startActiveSectionRecorder = (
    stream: MediaStream,
    overlapMs: number,
  ) => {
    const section = createSectionRecorder(stream, overlapMs);
    activeSectionRef.current = section;
    recorderRef.current = section.recorder;
    lastSpeechAtMsRef.current = section.startedAtMs;
  };

  const stopSectionRecorder = async (
    section: RecorderSection,
  ): Promise<{ blob: Blob | null; endTimeMs: number }> => {
    const recorder = section.recorder;
    const endTimeMs = getRecordingElapsedMs();

    if (recorder.state === "inactive") {
      return {
        blob:
          section.chunks.length > 0
            ? new Blob(section.chunks, { type: recorder.mimeType || mimeTypeRef.current })
            : null,
        endTimeMs,
      };
    }

    return new Promise((resolve) => {
      const mimeType = recorder.mimeType || mimeTypeRef.current;
      let settled = false;
      let timeoutId: number | null = null;

      const settle = () => {
        if (settled) return;
        settled = true;
        if (timeoutId !== null) {
          window.clearTimeout(timeoutId);
        }
        const blob =
          section.chunks.length > 0
            ? new Blob(section.chunks, { type: mimeType })
            : null;
        section.chunks = [];
        resolve({ blob, endTimeMs });
      };

      recorder.onstop = settle;
      timeoutId = window.setTimeout(() => {
        logger.warn(
          "[DebugTranscription] MediaRecorder stop timed out; finalizing available chunks",
        );
        settle();
      }, 2500);

      try {
        if (recorder.state !== "inactive") {
          recorder.requestData();
        }
        recorder.stop();
      } catch (error) {
        logger.error("[DebugTranscription] stopSectionRecorder failed", error);
        settle();
      }
    });
  };

  const saveSection = async (section: RecorderSection) => {
    const { blob, endTimeMs } = await stopSectionRecorder(section);
    if (!blob) return;
    const sectionDurationMs = endTimeMs - section.startedAtMs;
    const shouldKeep = shouldUploadSectionForTranscription({
      hasDetectedSpeech: section.hasDetectedSpeech,
      speechFrameCount: section.speechFrameCount,
      sectionDurationMs,
    });
    if (!shouldKeep) {
      return;
    }
    const item: SectionItem = {
      id: section.id,
      blob,
      url: URL.createObjectURL(blob),
      startMs: section.startedAtMs,
      endMs: endTimeMs,
      durationMs: sectionDurationMs,
      mimeType: blob.type || mimeTypeRef.current,
      transcripts: {},
    };
    setSections((current) => [...current, item]);
  };

  const addUploadedAudio = async (file: File) => {
    const mimeType = file.type || "audio/webm";
    const sectionUrl = URL.createObjectURL(file);
    const fullAudioUrl = URL.createObjectURL(file);
    const durationMs = await getAudioDurationMs(sectionUrl);
    const item: SectionItem = {
      id: makeSectionId(),
      blob: file,
      url: sectionUrl,
      startMs: 0,
      endMs: durationMs,
      durationMs,
      mimeType,
      transcripts: {},
    };
    setSections((current) => [...current, item]);
    replaceFullAudio({
      blob: file,
      url: fullAudioUrl,
      durationMs,
      mimeType,
      name: file.name || "audio-subido",
      source: "upload",
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

  const armSectionBoundaryControl = () => {
    if (!isRecordingRef.current || !streamRef.current?.active) {
      return;
    }
    if (sectionBoundaryTimerRef.current !== null) {
      window.clearTimeout(sectionBoundaryTimerRef.current);
    }
    sectionBoundaryTimerRef.current = window.setTimeout(() => {
      const currentSection = activeSectionRef.current;
      if (!currentSection) return;
      const sectionDurationMs =
        getRecordingElapsedMs() - currentSection.startedAtMs;
      if (shouldForceSectionCut(sectionDurationMs)) {
        void splitCurrentSectionWithOverlap();
      } else {
        armSectionBoundaryControl();
      }
    }, AUDIO_SEGMENTATION_CONFIG.maxSectionMs);
  };

  const flushCurrentSection = async (isFinal = false) => {
    const currentSection = activeSectionRef.current;
    const stream = streamRef.current;
    if (!currentSection) return;

    activeSectionRef.current = null;
    recorderRef.current = null;
    if (sectionBoundaryTimerRef.current !== null) {
      window.clearTimeout(sectionBoundaryTimerRef.current);
      sectionBoundaryTimerRef.current = null;
    }
    await saveSection(currentSection);
    if (!isFinal && stream?.active && isRecordingRef.current) {
      startActiveSectionRecorder(stream, 0);
      armSectionBoundaryControl();
    }
  };

  const finalizeRetiringSection = async () => {
    const retiringSection = retiringSectionRef.current;
    if (!retiringSection) {
      forcedSplitInFlightRef.current = false;
      return;
    }
    retiringSectionRef.current = null;
    await saveSection(retiringSection);
    forcedSplitInFlightRef.current = false;
  };

  const splitCurrentSectionWithOverlap = async () => {
    const stream = streamRef.current;
    const currentSection = activeSectionRef.current;
    if (
      !stream?.active ||
      !currentSection ||
      forcedSplitInFlightRef.current
    ) {
      return;
    }
    forcedSplitInFlightRef.current = true;
    if (sectionBoundaryTimerRef.current !== null) {
      window.clearTimeout(sectionBoundaryTimerRef.current);
      sectionBoundaryTimerRef.current = null;
    }
    retiringSectionRef.current = currentSection;
    activeSectionRef.current = null;
    startActiveSectionRecorder(stream, AUDIO_SEGMENTATION_CONFIG.forcedOverlapMs);
    armSectionBoundaryControl();
    overlapTimerRef.current = window.setTimeout(() => {
      overlapTimerRef.current = null;
      void finalizeRetiringSection();
    }, AUDIO_SEGMENTATION_CONFIG.forcedOverlapMs);
  };

  const startRecording = async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      mimeTypeRef.current = getBestSupportedAudioType();

      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = VAD_ANALYSER_FFT_SIZE;
      source.connect(analyser);
      analyserRef.current = analyser;
      vadBufferRef.current = new Float32Array(analyser.fftSize);

      const nowMs = Date.now();
      recordingStartedAtRef.current = nowMs;
      replaceFullAudio(null);
      setIsRecording(true);
      isRecordingRef.current = true;
      createFullSessionRecorder(stream);
      startActiveSectionRecorder(stream, 0);

      timerRef.current = window.setInterval(() => {
        setElapsedMs(getRecordingElapsedMs());
      }, 250);

      vadIntervalRef.current = window.setInterval(() => {
        const analyserNode = analyserRef.current;
        const vadBuffer = vadBufferRef.current;
        if (!analyserNode || !vadBuffer) return;

        analyserNode.getFloatTimeDomainData(vadBuffer);
        const sample = detectVoiceActivity(vadBuffer);
        const tickNowMs = getRecordingElapsedMs();
        const currentSection = activeSectionRef.current;
        if (currentSection) {
          const sectionDurationMs = tickNowMs - currentSection.startedAtMs;
          setVadDebug({
            sectionDurationMs,
            stableSilenceMs: Math.max(0, tickNowMs - lastSpeechAtMsRef.current),
            naturalPauseThresholdMs:
              getNaturalPauseThresholdMs(sectionDurationMs),
            rms: sample.rms,
            peak: sample.peak,
            isSpeech: sample.isSpeech,
          });
        }

        if (sample.isSpeech) {
          lastSpeechAtMsRef.current = tickNowMs;
          if (currentSection) {
            currentSection.hasDetectedSpeech = true;
            currentSection.speechFrameCount += 1;
          }
          if (retiringSectionRef.current) {
            retiringSectionRef.current.hasDetectedSpeech = true;
            retiringSectionRef.current.speechFrameCount += 1;
          }
          return;
        }

        if (forcedSplitInFlightRef.current) {
          return;
        }

        if (!currentSection) return;
        if (
          shouldFlushOnNaturalPause({
            nowMs: tickNowMs,
            sectionStartedAtMs: currentSection.startedAtMs,
            lastSpeechAtMs: lastSpeechAtMsRef.current,
            hasDetectedSpeech: currentSection.hasDetectedSpeech,
          })
        ) {
          void flushCurrentSection();
          return;
        }

        if (shouldForceSectionCut(tickNowMs - currentSection.startedAtMs)) {
          void splitCurrentSectionWithOverlap();
        }
      }, AUDIO_SEGMENTATION_CONFIG.vadPollIntervalMs);
      armSectionBoundaryControl();
    } catch (recordingError) {
      logger.error("[DebugTranscription] startRecording failed", recordingError);
      setError("No se pudo iniciar la grabacion.");
      cleanupMedia();
      setIsRecording(false);
      isRecordingRef.current = false;
    }
  };

  const stopRecording = () => {
    clearTimers();
    setIsRecording(false);
    isRecordingRef.current = false;
    setElapsedMs(0);
    setVadDebug(null);
    void (async () => {
      if (forcedSplitInFlightRef.current) {
        await finalizeRetiringSection();
      }
      await flushCurrentSection(true);
      const fullBlob = await stopFullSessionRecorder();
      if (fullBlob) {
        const durationMs = getRecordingElapsedMs();
        replaceFullAudio({
          blob: fullBlob,
          url: URL.createObjectURL(fullBlob),
          durationMs,
          mimeType: fullBlob.type || mimeTypeRef.current,
          name: `debug-transcripcion-${Date.now()}.webm`,
          source: "recording",
        });
      }
      cleanupMedia();
    })();
  };

  const clearSections = () => {
    for (const section of sections) {
      URL.revokeObjectURL(section.url);
    }
    replaceFullAudio(null);
    setSections([]);
  };

  const transcribeSection = async (
    section: SectionItem,
    provider: ProviderKey,
  ) => {
    const model = provider === "gemini" ? geminiModel : openaiModel;
    setBusyKey(`${section.id}:${provider}`);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", section.blob, `${section.id}.webm`);
      formData.append(
        "provider",
        provider === "gemini" ? "google_genai" : "openai",
      );
      formData.append("model", model);

      const requestStartedAt = performance.now();
      const response = await fetch(
        `${WORKER_URL}/api/v1/dev/transcription/debug`,
        {
          method: "POST",
          body: formData,
        },
      );
      const responseTimeMs = performance.now() - requestStartedAt;
      if (!response.ok) {
        const payload = await response.text();
        throw new Error(payload || "debug_transcription_failed");
      }
      const payload =
        (await response.json()) as SectionTranscriptionPayload;
      setSections((current) =>
        current.map((item) =>
          item.id === section.id
            ? {
                ...item,
                transcripts: {
                  ...item.transcripts,
                  [provider]: {
                    transcript: payload.transcript,
                    vadDecision: payload.vad_decision,
                    vadSpeechMs: payload.vad_speech_ms,
                    vadSpeechRatio: payload.vad_speech_ratio,
                    model: payload.model,
                    contentType: payload.content_type,
                    responseTimeMs,
                  },
                },
              }
            : item,
        ),
      );
    } catch (transcriptionError) {
      logger.error(
        "[DebugTranscription] transcribeSection failed",
        provider,
        transcriptionError,
      );
      setError(
        provider === "gemini"
          ? "Fallo la transcripcion con Gemini."
          : "Fallo la transcripcion con OpenAI.",
      );
    } finally {
      setBusyKey(null);
    }
  };

  const transcribeAll = async (provider: ProviderKey) => {
    for (const section of sections) {
      // eslint-disable-next-line no-await-in-loop
      await transcribeSection(section, provider);
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
    <div className="min-h-[180px] rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-800 whitespace-pre-wrap break-words">
      {value || <span className="text-slate-400">Sin transcripcion todavia.</span>}
    </div>
  );

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 py-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Debug de transcripcion
        </h1>
        <p className="max-w-3xl text-sm text-slate-600">
          Graba audio local, deja que se corte por pausas naturales y prueba la
          transcripcion de cada seccion con Gemini o OpenAI sin pasar por el
          flujo clinico normal.
        </p>
      </div>

      <Card className="grid gap-4 border border-slate-200 p-5 lg:grid-cols-[1.2fr_1fr]">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={isRecording ? stopRecording : startRecording}>
              {isRecording ? (
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
            <Button variant="outline" onClick={clearSections} disabled={isRecording}>
              Limpiar secciones
            </Button>
            <Badge variant="secondary">
              {isRecording ? "Grabando" : "En espera"}
            </Badge>
            <Badge variant="outline">{formatMs(elapsedMs)}</Badge>
            <Badge variant="outline">
              {sections.length} seccion{sections.length === 1 ? "" : "es"}
            </Badge>
          </div>

          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">Modelo Gemini</label>
              <Input
                value={geminiModel}
                onChange={(event) => setGeminiModel(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Modelo OpenAI</label>
              <Input
                value={openaiModel}
                onChange={(event) => setOpenaiModel(event.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <label
                htmlFor="debug-audio-upload"
                className={isRecording ? "pointer-events-none opacity-50" : ""}
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
              disabled={isRecording}
              onChange={handleAudioUpload}
            />
            <Button
              variant="outline"
              onClick={() => void transcribeAll("gemini")}
              disabled={sections.length === 0 || Boolean(busyKey)}
            >
              <WandSparkles className="mr-2 h-4 w-4" />
              Transcribir todo con Gemini
            </Button>
            <Button
              variant="outline"
              onClick={() => void transcribeAll("openai")}
              disabled={sections.length === 0 || Boolean(busyKey)}
            >
              <AudioLines className="mr-2 h-4 w-4" />
              Transcribir todo con OpenAI
            </Button>
          </div>

          {fullAudio ? (
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">
                    {fullAudio.source === "recording" ? "Grabacion completa" : "Audio subido"}
                  </Badge>
                  <Badge variant="outline">{formatMs(fullAudio.durationMs)}</Badge>
                  <Badge variant="outline">{fullAudio.mimeType}</Badge>
                </div>
                <Button asChild size="sm" variant="outline">
                  <a href={fullAudio.url} download={fullAudio.name}>
                    <Download className="mr-2 h-4 w-4" />
                    Descargar
                  </a>
                </Button>
              </div>
              <audio controls src={fullAudio.url} className="h-10 w-full" />
            </div>
          ) : null}
        </div>

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
          <p className="font-medium text-slate-900">Ruta de debug</p>
          <p className="mt-2">
            Worker: <code>{WORKER_URL}</code>
          </p>
          {vadDebug ? (
            <div className="mt-3 grid grid-cols-2 gap-2 rounded-md border border-slate-200 bg-white p-3 text-xs">
              <span className="text-slate-500">Estado VAD</span>
              <span className="text-right font-medium text-slate-900">
                {vadDebug.isSpeech ? "voz" : "silencio"}
              </span>
              <span className="text-slate-500">Seccion actual</span>
              <span className="text-right font-medium text-slate-900">
                {formatMs(vadDebug.sectionDurationMs)}
              </span>
              <span className="text-slate-500">Silencio estable</span>
              <span className="text-right font-medium text-slate-900">
                {Math.round(vadDebug.stableSilenceMs)} ms
              </span>
              <span className="text-slate-500">Umbral de corte</span>
              <span className="text-right font-medium text-slate-900">
                {vadDebug.naturalPauseThresholdMs} ms
              </span>
              <span className="text-slate-500">RMS / pico</span>
              <span className="text-right font-medium text-slate-900">
                {vadDebug.rms.toFixed(4)} / {vadDebug.peak.toFixed(4)}
              </span>
            </div>
          ) : null}
          <p className="mt-2">
            Gemini usa bytes inline solo para este debug. OpenAI recibe el audio
            transcoding a WAV antes de transcribir.
          </p>
          <p className="mt-2">
            Si una seccion sale vacia, revisa el `vad_decision` y el ratio de
            voz en la respuesta.
          </p>
        </div>
      </Card>

      <div className="grid gap-4">
        {sections.map((section, index) => {
          const geminiResult = section.transcripts.gemini;
          const openaiResult = section.transcripts.openai;
          return (
            <Card key={section.id} className="border border-slate-200 p-5">
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge>{`Seccion ${index + 1}`}</Badge>
                    <Badge variant="outline">
                      {formatMs(section.startMs)} - {formatMs(section.endMs)}
                    </Badge>
                    <Badge variant="outline">{formatMs(section.durationMs)}</Badge>
                    <Badge variant="outline">{section.mimeType}</Badge>
                  </div>
                  <audio controls src={section.url} className="h-10 w-full max-w-md" />
                </div>

                <div className="flex flex-wrap gap-2">
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
                  <Button
                    variant="outline"
                    onClick={() => void transcribeSection(section, "openai")}
                    disabled={busyKey !== null}
                  >
                    {busyKey === `${section.id}:openai` ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <AudioLines className="mr-2 h-4 w-4" />
                    )}
                    OpenAI
                  </Button>
                </div>

                <div className="grid gap-4 xl:grid-cols-2">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">Gemini</span>
                        {geminiResult ? (
                          <Badge variant="secondary">{geminiResult.model}</Badge>
                        ) : null}
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => void copyText(geminiResult?.transcript || "")}
                        disabled={!geminiResult?.transcript}
                      >
                        <Copy className="mr-2 h-4 w-4" />
                        Copiar
                      </Button>
                    </div>
                    {renderTranscriptSurface(geminiResult?.transcript || "")}
                    {geminiResult ? (
                      <p className="text-xs text-slate-500">
                        VAD: {geminiResult.vadDecision} | voz{" "}
                        {geminiResult.vadSpeechMs} ms | ratio{" "}
                        {geminiResult.vadSpeechRatio.toFixed(3)} | respuesta{" "}
                        {(geminiResult.responseTimeMs / 1000).toFixed(1)} s
                      </p>
                    ) : null}
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">OpenAI</span>
                        {openaiResult ? (
                          <Badge variant="secondary">{openaiResult.model}</Badge>
                        ) : null}
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => void copyText(openaiResult?.transcript || "")}
                        disabled={!openaiResult?.transcript}
                      >
                        <Copy className="mr-2 h-4 w-4" />
                        Copiar
                      </Button>
                    </div>
                    {renderTranscriptSurface(openaiResult?.transcript || "")}
                    {openaiResult ? (
                      <p className="text-xs text-slate-500">
                        VAD: {openaiResult.vadDecision} | voz{" "}
                        {openaiResult.vadSpeechMs} ms | ratio{" "}
                        {openaiResult.vadSpeechRatio.toFixed(3)} | respuesta{" "}
                        {(openaiResult.responseTimeMs / 1000).toFixed(1)} s
                      </p>
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
            Graba una muestra y la pagina ira creando secciones cuando detecte
            pausas naturales.
          </p>
        </>
      ) : null}
    </div>
  );
}
