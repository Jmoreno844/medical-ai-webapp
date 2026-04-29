import { useState, useEffect, useRef } from "react";
import { UseVoiceRecorderReturn } from "./types";
import { getBestSupportedAudioType } from "./utils";
import {
  createRecordingSession,
  finishRecordingSession,
  generateAudioUploadUrl,
  generateSectionUploadUrl,
  registerAudioSection,
  uploadAudioToCloud,
} from "./uploadService";
import {
  LocalAudioSection,
  deleteLocalSectionBlob,
  listPendingSections,
  saveLocalSection,
  updateLocalSection,
} from "./sectionQueue";
import {
  AUDIO_SEGMENTATION_CONFIG,
  VAD_ANALYSER_FFT_SIZE,
  detectVoiceActivity,
  shouldFlushOnNaturalPause,
  shouldForceSectionCut,
  shouldUploadSectionForTranscription,
} from "./vad";
import axiosInstance from "@/commons/utils/axiosInstance";
import { logger } from "@/lib/logger";

type RecorderSection = {
  id: string;
  recorder: MediaRecorder;
  chunks: Blob[];
  startedAtMs: number;
  overlapMs: number;
  hasDetectedSpeech: boolean;
  speechFrameCount: number;
};

type BrowserAudioContextCtor = typeof AudioContext & {
  new (): AudioContext;
};
/**
 * Checks if audio exists for an encounter
 *
 * @param encounterId - ID of the encounter to check
 * @returns Object containing exists flag and duration if exists
 */
const checkAudioExists = async (encounterId: number) => {
  try {
    const response = await axiosInstance.get(
      `/api/v1/encounters/${encounterId}/audio/exists`,
    );

    // With axiosInstance, the data is already parsed as JSON
    const data = response.data;
    return {
      exists:
        data === true || (typeof data === "object" && data.exists === true),
      duration: typeof data === "object" && data.duration ? data.duration : 0,
      has_been_transcribed:
        typeof data === "object" && data.has_been_transcribed === true,
      expires_at:
        typeof data === "object" && data.expires_at ? data.expires_at : null,
      is_expired: typeof data === "object" && data.is_expired === true,
    };
  } catch (error) {
    logger.error("[VOICE_RECORDER] Error checking audio existence:", error);
    return {
      exists: false,
      duration: 0,
      has_been_transcribed: false,
      expires_at: null,
      is_expired: false,
    };
  }
};
/**
 * Custom hook to manage voice recording functionality
 *
 * Handles recording, pausing, stopping, and deleting audio recordings
 * with support for saving to a transcription document
 *
 * @param transcriptionDocId - Optional ID of the transcription document to associate with recordings
 * @returns Object containing recording state and control functions
 */
export const useVoiceRecorder = (
  encounterId: number, // Add encounterId parameter
  transcriptionDocId?: number,
): UseVoiceRecorderReturn => {
  // State for recording status
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [duration, setDuration] = useState(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioExists, setAudioExists] = useState(false);
  const [audioExpiresAt, setAudioExpiresAt] = useState<string | null>(null);
  const [isAudioExpired, setIsAudioExpired] = useState(false);
  const [isCheckingAudio, setIsCheckingAudio] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [hasBeenTranscribed, setHasBeenTranscribed] = useState(false);
  const [recordingSessionId, setRecordingSessionId] = useState<string | null>(
    null,
  );
  const [pendingAudioSections, setPendingAudioSections] = useState(0);

  // Refs for managing media recorder and timer
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sectionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const overlapTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef<number>(0);
  const nextSectionIndexRef = useRef(0);
  const recordingSessionIdRef = useRef<string | null>(null);
  const isRecordingRef = useRef(false);
  const isPausedRef = useRef(false);
  const isStoppingRef = useRef(false);
  const audioMimeTypeRef = useRef("audio/webm");
  const sectionFlushRef = useRef<Promise<void> | null>(null);
  const activeSectionRef = useRef<RecorderSection | null>(null);
  const retiringSectionRef = useRef<RecorderSection | null>(null);
  const forcedSplitInFlightRef = useRef(false);
  const lastSpeechAtMsRef = useRef(0);
  const segmentationModeRef = useRef<"vad" | "timer">("timer");
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const vadBufferRef = useRef<Float32Array | null>(null);
  const vadIntervalRef = useRef<number | null>(null);

  // Store the transcription document ID
  const transcriptionDocIdRef = useRef<number | undefined>(transcriptionDocId);

  // Update ref when prop changes
  useEffect(() => {
    transcriptionDocIdRef.current = transcriptionDocId;
  }, [transcriptionDocId]);

  // Effect to check audio and reset state when encounterId changes
  useEffect(() => {
    // --- State Reset ---
    logger.debug(
      `[VOICE_RECORDER] Effect running for encounterId: ${encounterId}. Resetting state.`,
    );
    setIsRecording(false);
    setIsPaused(false);
    setDuration(0);
    setAudioBlob(null);
    setAudioExists(false);
    setAudioExpiresAt(null);
    setIsAudioExpired(false);
    setHasBeenTranscribed(false);
    chunksRef.current = [];
    nextSectionIndexRef.current = 0;
    recordingSessionIdRef.current = null;
    isRecordingRef.current = false;
    isPausedRef.current = false;
    isStoppingRef.current = false;
    activeSectionRef.current = null;
    retiringSectionRef.current = null;
    forcedSplitInFlightRef.current = false;
    setRecordingSessionId(null);
    setPendingAudioSections(0);
    if (timerRef.current) clearInterval(timerRef.current);
    if (sectionTimerRef.current) clearTimeout(sectionTimerRef.current);
    if (overlapTimerRef.current) clearTimeout(overlapTimerRef.current);
    if (vadIntervalRef.current !== null)
      window.clearInterval(vadIntervalRef.current);
    timerRef.current = null;
    sectionTimerRef.current = null;
    overlapTimerRef.current = null;
    vadIntervalRef.current = null;

    // Stop any active recorder
    if (mediaRecorderRef.current?.state !== "inactive") {
      try {
        mediaRecorderRef.current?.stop();
      } catch (e) {
        logger.warn("Error stopping previous recorder:", e);
      }
    }
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaRecorderRef.current = null;
    mediaStreamRef.current = null;
    sourceNodeRef.current?.disconnect();
    analyserRef.current?.disconnect();
    sourceNodeRef.current = null;
    analyserRef.current = null;
    vadBufferRef.current = null;
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      void audioContextRef.current.close();
    }
    audioContextRef.current = null;

    const checkExistingAudio = async () => {
      if (encounterId > 0) {
        setIsCheckingAudio(true);
        logger.debug(
          `[VOICE_RECORDER] Checking audio for encounter ${encounterId}`,
        );
        try {
          const {
            exists,
            duration: existingDuration,
            has_been_transcribed,
            expires_at,
            is_expired,
          } = await checkAudioExists(encounterId);

          logger.debug(
            `[VOICE_RECORDER] Audio check result for ${encounterId}:`,
            {
              exists,
              existingDuration,
              has_been_transcribed,
              expires_at,
              is_expired,
            },
          );

          setAudioExists(exists);
          setDuration(exists ? existingDuration : 0);
          setAudioExpiresAt(exists ? expires_at : null);
          setIsAudioExpired(exists ? is_expired : false);
          setHasBeenTranscribed(exists ? has_been_transcribed : false);
        } catch (error) {
          logger.error(
            `[VOICE_RECORDER] Error checking audio for ${encounterId}:`,
            error,
          );
          setAudioExists(false);
          setDuration(0);
          setAudioExpiresAt(null);
          setIsAudioExpired(false);
          setHasBeenTranscribed(false);
        } finally {
          setIsCheckingAudio(false);
          logger.debug(
            `[VOICE_RECORDER] Finished checking audio for ${encounterId}`,
          );
        }
      } else {
        logger.debug(
          `[VOICE_RECORDER] Invalid encounterId (${encounterId}), skipping check.`,
        );
        setAudioExists(false);
        setDuration(0);
        setAudioExpiresAt(null);
        setIsAudioExpired(false);
        setHasBeenTranscribed(false);
        setIsCheckingAudio(false);
      }
    };

    checkExistingAudio();

    return () => {
      logger.debug(
        `[VOICE_RECORDER] Cleanup effect for encounter ${encounterId}`,
      );
      if (timerRef.current) clearInterval(timerRef.current);
      if (sectionTimerRef.current) clearTimeout(sectionTimerRef.current);
      if (mediaRecorderRef.current?.state !== "inactive") {
        try {
          mediaRecorderRef.current?.stop();
        } catch {
          /* ignore */
        }
      }
    };
  }, [encounterId]);

  const refreshPendingSectionCount = async () => {
    const sections = await listPendingSections(encounterId);
    setPendingAudioSections(sections.length);
  };

  const processPendingSections = async ({
    finishSessionsWhenDrained = false,
  }: { finishSessionsWhenDrained?: boolean } = {}) => {
    const sections = await listPendingSections(encounterId);
    setPendingAudioSections(sections.length);
    const processedSessionIds = new Set<string>();

    for (const section of sections) {
      if (!section.blob) {
        await updateLocalSection(section.local_section_id, {
          status: "failed_final",
        });
        continue;
      }

      try {
        await updateLocalSection(section.local_section_id, {
          status: "upload_url_pending",
          retry_count: section.retry_count + 1,
        });

        const alreadyUploaded =
          Boolean(section.gcs_object_name) &&
          ["uploaded", "registering"].includes(section.status);
        const uploadInfo = alreadyUploaded
          ? {
              uploadUrl: "",
              gcsObjectName: section.gcs_object_name as string,
            }
          : await generateSectionUploadUrl(
              section.recording_session_id,
              section.local_section_id,
              section.section_index,
              section.content_type,
            );

        if (!uploadInfo) {
          await updateLocalSection(section.local_section_id, {
            status: "failed_retryable",
          });
          continue;
        }

        let gcsObjectName = uploadInfo.gcsObjectName;
        if (!alreadyUploaded) {
          await updateLocalSection(section.local_section_id, {
            status: "uploading",
            gcs_object_name: gcsObjectName,
          });
          const uploadSuccess = await uploadAudioToCloud(
            section.blob,
            uploadInfo.uploadUrl,
            section.content_type,
          );
          if (!uploadSuccess) {
            await updateLocalSection(section.local_section_id, {
              status: "failed_retryable",
            });
            continue;
          }
          await updateLocalSection(section.local_section_id, {
            status: "uploaded",
            gcs_object_name: gcsObjectName,
          });
        } else {
          gcsObjectName = section.gcs_object_name as string;
        }

        await updateLocalSection(section.local_section_id, {
          status: "registering",
          gcs_object_name: gcsObjectName,
        });
        const registerResult = await registerAudioSection(
          section.recording_session_id,
          {
            client_section_id: section.local_section_id,
            section_index: section.section_index,
            start_time_ms: section.start_time_ms,
            end_time_ms: section.end_time_ms,
            overlap_ms: section.overlap_ms,
            gcs_object_name: gcsObjectName,
            content_type: section.content_type,
            byte_size: section.blob.size,
          },
        );

        if (!registerResult.success) {
          await updateLocalSection(section.local_section_id, {
            status: "failed_retryable",
          });
          continue;
        }

        await updateLocalSection(section.local_section_id, {
          status: "registered",
          backend_section_id: registerResult.backendSectionId,
        });
        await deleteLocalSectionBlob(section.local_section_id);
        processedSessionIds.add(section.recording_session_id);
      } catch (error) {
        logger.error(
          "[VOICE_RECORDER] Error processing pending section:",
          error,
        );
        await updateLocalSection(section.local_section_id, {
          status: "failed_retryable",
        });
      }
    }

    await refreshPendingSectionCount();
    if (finishSessionsWhenDrained && processedSessionIds.size > 0) {
      const remainingSections = await listPendingSections(encounterId);
      if (remainingSections.length === 0) {
        await Promise.all(
          Array.from(processedSessionIds).map((sessionId) =>
            finishRecordingSession(sessionId),
          ),
        );
      }
    }
  };

  useEffect(() => {
    void processPendingSections({ finishSessionsWhenDrained: true });
    const handleOnline = () => {
      void processPendingSections({
        finishSessionsWhenDrained: !isRecordingRef.current,
      });
    };
    window.addEventListener("online", handleOnline);
    return () => window.removeEventListener("online", handleOnline);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [encounterId]);

  const clearSectionBoundaryTimers = () => {
    if (sectionTimerRef.current) {
      clearTimeout(sectionTimerRef.current);
      sectionTimerRef.current = null;
    }
    if (overlapTimerRef.current) {
      clearTimeout(overlapTimerRef.current);
      overlapTimerRef.current = null;
    }
  };

  const teardownVadMonitoring = async () => {
    clearSectionBoundaryTimers();
    if (vadIntervalRef.current !== null) {
      window.clearInterval(vadIntervalRef.current);
      vadIntervalRef.current = null;
    }
    sourceNodeRef.current?.disconnect();
    analyserRef.current?.disconnect();
    sourceNodeRef.current = null;
    analyserRef.current = null;
    vadBufferRef.current = null;
    const audioContext = audioContextRef.current;
    audioContextRef.current = null;
    if (audioContext && audioContext.state !== "closed") {
      await audioContext.close();
    }
  };

  const queueSectionWork = (work: () => Promise<void>) => {
    const previous =
      sectionFlushRef.current?.catch((error) => {
        logger.error("[VOICE_RECORDER] Section flush chain error:", error);
      }) ?? Promise.resolve();

    const next = previous.then(work);
    sectionFlushRef.current = next;
    return next.finally(() => {
      if (sectionFlushRef.current === next) {
        sectionFlushRef.current = null;
      }
    });
  };

  const createSectionRecorder = (
    stream: MediaStream,
    mimeType: string,
    overlapMs: number,
  ): RecorderSection => {
    const mediaRecorder = new MediaRecorder(stream, {
      mimeType,
      audioBitsPerSecond: 24000,
    });

    const section: RecorderSection = {
      id: crypto.randomUUID(),
      recorder: mediaRecorder,
      chunks: [],
      startedAtMs: Date.now() - recordingStartedAtRef.current,
      overlapMs,
      hasDetectedSpeech: false,
      speechFrameCount: 0,
    };

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        section.chunks.push(event.data);
      }
    };

    mediaRecorder.onerror = (event) => {
      logger.error("[VOICE_RECORDER] Section recorder error:", event);
    };

    mediaRecorder.start();
    return section;
  };

  const startActiveSectionRecorder = (
    stream: MediaStream,
    overlapMs: number,
  ) => {
    const nextSection = createSectionRecorder(
      stream,
      audioMimeTypeRef.current,
      overlapMs,
    );
    activeSectionRef.current = nextSection;
    mediaRecorderRef.current = nextSection.recorder;
    lastSpeechAtMsRef.current = nextSection.startedAtMs;
  };

  const stopSectionRecorder = async (
    section: RecorderSection,
  ): Promise<{ blob: Blob | null; endTimeMs: number }> => {
    const mediaRecorder = section.recorder;
    const endTimeMs = Date.now() - recordingStartedAtRef.current;

    if (mediaRecorder.state === "inactive") {
      const blob =
        section.chunks.length > 0
          ? new Blob(section.chunks, {
              type: mediaRecorder.mimeType || audioMimeTypeRef.current,
            })
          : null;
      return { blob, endTimeMs };
    }

    return new Promise((resolve) => {
      const mimeType = mediaRecorder.mimeType || audioMimeTypeRef.current;
      let settled = false;
      let timeoutId: ReturnType<typeof setTimeout> | null = null;

      const settle = () => {
        if (settled) {
          return;
        }
        settled = true;
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
        const blob =
          section.chunks.length > 0
            ? new Blob(section.chunks, { type: mimeType })
            : null;
        section.chunks = [];
        resolve({ blob, endTimeMs });
      };

      mediaRecorder.onstop = settle;
      timeoutId = setTimeout(() => {
        logger.warn("[VOICE_RECORDER] MediaRecorder stop timed out; finalizing available chunks");
        settle();
      }, 2500);

      try {
        if (mediaRecorder.state === "paused") {
          mediaRecorder.resume();
        }
        if (mediaRecorder.state !== "inactive") {
          mediaRecorder.requestData();
        }
        mediaRecorder.stop();
      } catch (error) {
        logger.error(
          "[VOICE_RECORDER] Failed to stop section recorder:",
          error,
        );
        settle();
      }
    });
  };

  const saveSectionBlob = async (
    blob: Blob,
    startTimeMs: number,
    endTimeMs: number,
    overlapMs: number,
    hasDetectedSpeech: boolean,
    speechFrameCount: number,
  ) => {
    const activeSessionId = recordingSessionIdRef.current;
    const documentId = transcriptionDocIdRef.current;
    if (!activeSessionId || !documentId || blob.size === 0) {
      return;
    }

    const sectionIndex = nextSectionIndexRef.current;
    const sectionDurationMs = endTimeMs - startTimeMs;

    const contentType = blob.type || audioMimeTypeRef.current;
    const localSectionId = crypto.randomUUID();
    const now = new Date().toISOString();
    const shouldUpload = shouldUploadSectionForTranscription({
      hasDetectedSpeech,
      speechFrameCount,
      sectionDurationMs,
    });
    const localSection: LocalAudioSection = {
      local_section_id: localSectionId,
      recording_session_id: activeSessionId,
      encounter_id: encounterId,
      document_id: documentId,
      section_index: sectionIndex,
      start_time_ms: startTimeMs,
      end_time_ms: endTimeMs,
      overlap_ms: overlapMs,
      blob: shouldUpload ? blob : undefined,
      content_type: contentType,
      status: shouldUpload ? "recorded" : "discarded_no_voice",
      retry_count: 0,
      speech_frame_count: speechFrameCount,
      discard_reason: shouldUpload
        ? undefined
        : hasDetectedSpeech
          ? "insufficient_voice_frames"
          : "no_voice_detected",
      created_at: now,
      updated_at: now,
    };

    await saveLocalSection(localSection);
    if (!shouldUpload) {
      logger.debug("[VOICE_RECORDER] Discarded section without enough voice", {
        sectionIndex,
        sectionDurationMs,
        speechFrameCount,
        discardReason: localSection.discard_reason,
      });
      nextSectionIndexRef.current += 1;
      return;
    }

    chunksRef.current.push(blob);
    setAudioBlob(new Blob(chunksRef.current, { type: contentType }));
    nextSectionIndexRef.current += 1;
    await processPendingSections();
  };

  const finalizeSection = (section: RecorderSection | null) => {
    if (!section) {
      return Promise.resolve();
    }

    return queueSectionWork(async () => {
      const { blob, endTimeMs } = await stopSectionRecorder(section);
      if (blob) {
        await saveSectionBlob(
          blob,
          section.startedAtMs,
          endTimeMs,
          section.overlapMs,
          section.hasDetectedSpeech,
          section.speechFrameCount,
        );
      }
    });
  };

  const armSectionBoundaryControl = () => {
    if (!isRecordingRef.current || isPausedRef.current) {
      return;
    }

    if (sectionTimerRef.current) {
      clearTimeout(sectionTimerRef.current);
    }

    const timeoutMs =
      segmentationModeRef.current === "vad"
        ? AUDIO_SEGMENTATION_CONFIG.maxSectionMs
        : AUDIO_SEGMENTATION_CONFIG.fallbackSectionMs;

    sectionTimerRef.current = setTimeout(() => {
      if (!isRecordingRef.current || isPausedRef.current) {
        return;
      }

      if (segmentationModeRef.current === "vad") {
        const currentSection = activeSectionRef.current;
        if (!currentSection) {
          return;
        }
        const sectionDurationMs =
          Date.now() -
          recordingStartedAtRef.current -
          currentSection.startedAtMs;
        if (shouldForceSectionCut(sectionDurationMs)) {
          void splitCurrentSectionWithOverlap();
        } else {
          armSectionBoundaryControl();
        }
        return;
      }

      void flushCurrentSection().finally(() => {
        if (isRecordingRef.current && !isPausedRef.current) {
          armSectionBoundaryControl();
        }
      });
    }, timeoutMs);
  };

  const flushCurrentSection = (isFinal = false) => {
    const currentSection = activeSectionRef.current;
    if (!currentSection) {
      return Promise.resolve();
    }

    activeSectionRef.current = null;
    mediaRecorderRef.current = null;
    clearSectionBoundaryTimers();

    return finalizeSection(currentSection).then(() => {
      const stream = mediaStreamRef.current;
      if (
        !isFinal &&
        stream?.active &&
        isRecordingRef.current &&
        !isPausedRef.current
      ) {
        startActiveSectionRecorder(stream, 0);
        armSectionBoundaryControl();
      }
    });
  };

  const finalizeRetiringSection = () => {
    const retiringSection = retiringSectionRef.current;
    if (!retiringSection) {
      forcedSplitInFlightRef.current = false;
      return Promise.resolve();
    }

    retiringSectionRef.current = null;
    return finalizeSection(retiringSection).finally(() => {
      forcedSplitInFlightRef.current = false;
    });
  };

  const splitCurrentSectionWithOverlap = () => {
    const stream = mediaStreamRef.current;
    const currentSection = activeSectionRef.current;

    if (
      !stream?.active ||
      !currentSection ||
      forcedSplitInFlightRef.current ||
      isPausedRef.current
    ) {
      return Promise.resolve();
    }

    forcedSplitInFlightRef.current = true;
    clearSectionBoundaryTimers();
    retiringSectionRef.current = currentSection;
    startActiveSectionRecorder(
      stream,
      AUDIO_SEGMENTATION_CONFIG.forcedOverlapMs,
    );
    armSectionBoundaryControl();

    overlapTimerRef.current = setTimeout(() => {
      overlapTimerRef.current = null;
      void finalizeRetiringSection();
    }, AUDIO_SEGMENTATION_CONFIG.forcedOverlapMs);

    return Promise.resolve();
  };

  const evaluateVoiceActivity = () => {
    const analyser = analyserRef.current;
    const buffer = vadBufferRef.current;
    const currentSection = activeSectionRef.current;

    if (
      !analyser ||
      !buffer ||
      !currentSection ||
      !isRecordingRef.current ||
      isPausedRef.current
    ) {
      return;
    }

    analyser.getFloatTimeDomainData(buffer);
    const sample = detectVoiceActivity(buffer);
    const nowMs = Date.now() - recordingStartedAtRef.current;

    if (sample.isSpeech) {
      lastSpeechAtMsRef.current = nowMs;
      currentSection.hasDetectedSpeech = true;
      currentSection.speechFrameCount += 1;
      if (retiringSectionRef.current) {
        retiringSectionRef.current.hasDetectedSpeech = true;
        retiringSectionRef.current.speechFrameCount += 1;
      }
      return;
    }

    if (forcedSplitInFlightRef.current) {
      return;
    }

    if (
      shouldFlushOnNaturalPause({
        nowMs,
        sectionStartedAtMs: currentSection.startedAtMs,
        lastSpeechAtMs: lastSpeechAtMsRef.current,
        hasDetectedSpeech: currentSection.hasDetectedSpeech,
      })
    ) {
      void flushCurrentSection();
    }
  };

  const enableVadSegmentation = async (stream: MediaStream) => {
    const AudioContextCtor = (window.AudioContext ??
      (
        window as Window & {
          webkitAudioContext?: BrowserAudioContextCtor;
        }
      ).webkitAudioContext) as BrowserAudioContextCtor | undefined;

    if (!AudioContextCtor) {
      segmentationModeRef.current = "timer";
      return;
    }

    try {
      const audioContext = new AudioContextCtor();
      const sourceNode = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = VAD_ANALYSER_FFT_SIZE;
      analyser.smoothingTimeConstant = 0.15;
      sourceNode.connect(analyser);

      audioContextRef.current = audioContext;
      sourceNodeRef.current = sourceNode;
      analyserRef.current = analyser;
      vadBufferRef.current = new Float32Array(analyser.fftSize);
      segmentationModeRef.current = "vad";
      await audioContext.resume();

      vadIntervalRef.current = window.setInterval(
        evaluateVoiceActivity,
        AUDIO_SEGMENTATION_CONFIG.vadPollIntervalMs,
      );
    } catch (error) {
      logger.warn(
        "[VOICE_RECORDER] Falling back to timer segmentation because VAD setup failed:",
        error,
      );
      segmentationModeRef.current = "timer";
      await teardownVadMonitoring();
    }
  };

  /**
   * Start recording audio
   */
  const startRecording = async () => {
    try {
      let nextRecordingSessionId = recordingSessionIdRef.current;
      if (transcriptionDocIdRef.current) {
        nextRecordingSessionId = await createRecordingSession(
          encounterId,
          transcriptionDocIdRef.current,
        );
        if (!nextRecordingSessionId) {
          logger.error("[VOICE_RECORDER] Could not create recording session");
          return;
        }
        recordingSessionIdRef.current = nextRecordingSessionId;
        setRecordingSessionId(nextRecordingSessionId);
      }

      // 1. Define optimized audio constraints
      const audioConstraints = {
        audio: {
          channelCount: 1, // Mono audio (instead of stereo)
          sampleRate: 16000, // 16kHz is good for voice (lower than default)
          echoCancellation: true, // Improve voice clarity
          noiseSuppression: true, // Reduce background noise
        },
      };

      // 2. Get audio stream with optimized constraints
      const stream =
        await navigator.mediaDevices.getUserMedia(audioConstraints);

      // 3. Find best supported audio format
      const supportedType = getBestSupportedAudioType();

      // 4. Create MediaRecorder with optimized settings
      mediaStreamRef.current = stream;
      audioMimeTypeRef.current = supportedType;
      chunksRef.current = [];
      const resumeDurationSeconds = audioExists && !isAudioExpired ? duration : 0;
      recordingStartedAtRef.current = Date.now() - resumeDurationSeconds * 1000;
      nextSectionIndexRef.current = 0;
      activeSectionRef.current = null;
      retiringSectionRef.current = null;
      forcedSplitInFlightRef.current = false;
      segmentationModeRef.current = "timer";
      await teardownVadMonitoring();

      if (isAudioExpired) {
        setDuration(0);
        setAudioExpiresAt(null);
        setIsAudioExpired(false);
      }

      startActiveSectionRecorder(stream, 0);
      await enableVadSegmentation(stream);
      isRecordingRef.current = true;
      isPausedRef.current = false;
      setIsRecording(true);
      setIsPaused(false);
      timerRef.current = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
      armSectionBoundaryControl();
    } catch (error) {
      logger.error("Error starting recording:", error);
      setIsRecording(false);
    }
  };

  /**
   * Pause or resume the current recording
   *
   * Toggles between paused and recording states, managing the timer accordingly
   */
  const pauseResumeRecording = () => {
    if (!mediaRecorderRef.current || !isRecordingRef.current || isStoppingRef.current) {
      return;
    }

    try {
      if (isPausedRef.current) {
        // Resume recording
        if (mediaRecorderRef.current.state === "paused") {
          mediaRecorderRef.current.resume();
        }
        if (timerRef.current) {
          clearInterval(timerRef.current);
        }
        timerRef.current = setInterval(() => {
          setDuration((prev) => prev + 1);
        }, 1000);
        isPausedRef.current = false;
        setIsPaused(false);
        armSectionBoundaryControl();
      } else {
        // Pause recording
        isPausedRef.current = true;
        setIsPaused(true);
        clearSectionBoundaryTimers();
        if (forcedSplitInFlightRef.current) {
          void finalizeRetiringSection();
        }
        if (mediaRecorderRef.current.state === "recording") {
          mediaRecorderRef.current.pause();
        }
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      }
    } catch (error) {
      logger.error("Error pausing/resuming recording:", error);
    }
  };

  /**
   * Stop the current recording
   *
   * Handles resuming if paused, then stops the recording and cleans up resources
   */
  const stopRecording = async () => {
    if (isStoppingRef.current) {
      return;
    }

    if (
      mediaRecorderRef.current ||
      activeSectionRef.current ||
      retiringSectionRef.current
    ) {
      isStoppingRef.current = true;
      isRecordingRef.current = false;
      isPausedRef.current = false;
      setIsRecording(false);
      setIsPaused(false);
      clearSectionBoundaryTimers();
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }

      // If paused, we need to resume first before stopping
      const recorderToStop = mediaRecorderRef.current;
      if (isPaused && recorderToStop?.state === "paused") {
        try {
          recorderToStop.resume();
        } catch (error) {
          logger.error("Error resuming recording before stop:", error);
        }
      }

      // Now stop the recording
      try {
        await teardownVadMonitoring();

        if (forcedSplitInFlightRef.current) {
          await finalizeRetiringSection();
        }

        await flushCurrentSection(true);

        if (recordingSessionIdRef.current) {
          await finishRecordingSession(recordingSessionIdRef.current);
        }

        // Sectioned recordings upload each chunk to GCS as they are captured.
        // Whole-audio upload is only needed when no recording session exists.
        if (transcriptionDocIdRef.current && !recordingSessionIdRef.current) {
          try {
            if (!encounterId || encounterId <= 0) {
              logger.error(
                "[VOICE_RECORDER] Invalid encounterId in stopRecording:",
                encounterId,
              );
              return;
            }
            const uploadUrl = await generateAudioUploadUrl(
              encounterId,
              duration,
            );

            if (!uploadUrl) {
              logger.error("[VOICE_RECORDER] Failed to get upload URL");
              return;
            }

            // Get the current audio blob
            const currentAudioBlob =
              chunksRef.current.length > 0
                ? new Blob(chunksRef.current, {
                    type: audioMimeTypeRef.current,
                  })
                : null;

            if (currentAudioBlob) {
              // Upload using the dedicated function
              const uploadSuccess = await uploadAudioToCloud(
                currentAudioBlob,
                uploadUrl,
                audioMimeTypeRef.current,
              );

              if (!uploadSuccess) {
                logger.error(
                  "[VOICE_RECORDER] Failed to upload audio recording",
                );
              } else {
                setIsAudioExpired(false);
                setAudioExpiresAt(null);
              }
            } else {
              logger.error(
                "[VOICE_RECORDER] No audio data available to upload",
              );
            }
          } catch (error) {
            logger.error(
              "[VOICE_RECORDER] Error during upload process:",
              error,
            );
          }
        } else if (recordingSessionIdRef.current) {
          logger.debug(
            "[VOICE_RECORDER] Sectioned transcription session finished; skipping whole-audio upload because sections were already uploaded to GCS",
          );
        } else {
          logger.debug(
            "[VOICE_RECORDER] No transcription document ID available for whole-audio upload; skipping encounter audio upload",
          );
        }
        const finalAudioBlob = new Blob(chunksRef.current, {
          type: audioMimeTypeRef.current,
        });
        const fileSizeKB = finalAudioBlob.size / 1024;
        logger.debug(
          `[VOICE_RECORDER] Recording complete: ${fileSizeKB.toFixed(
            2,
          )} KB, ${duration} seconds`,
        );
        setAudioExists(true);
      } catch (error) {
        logger.error("Error stopping recording:", error);
      } finally {
        mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
        mediaRecorderRef.current = null;
        activeSectionRef.current = null;
        retiringSectionRef.current = null;
        forcedSplitInFlightRef.current = false;
        isStoppingRef.current = false;
      }
    }
  };

  /**
   * Delete the current recording
   *
   * Resets all recording state and stops any active recording
   * Also deletes the audio file from the server if it exists
   */
  const deleteRecording = async () => {
    setIsDeleting(true); // Set deleting state to true

    if (mediaRecorderRef.current?.state !== "inactive") {
      try {
        mediaRecorderRef.current?.stop();
      } catch (error) {
        logger.error("Error stopping recorder during deletion:", error);
      }
    }

    // Delete from server if audio exists
    if (audioExists) {
      try {
        if (encounterId && encounterId > 0) {
          logger.debug(
            `[VOICE_RECORDER] Attempting to delete audio for encounter ${encounterId}`,
          );
          await axiosInstance.delete(`/api/v1/encounters/${encounterId}/audio`);
          logger.debug(
            "[VOICE_RECORDER] Server delete request sent for encounter",
            encounterId,
          );
        } else {
          logger.warn(
            "[VOICE_RECORDER] Invalid encounterId in deleteRecording:",
            encounterId,
          );
        }
      } catch (error) {
        logger.error(
          "[VOICE_RECORDER] Error deleting audio from server:",
          error,
        );
      }
    }

    // Reset all states
    setAudioBlob(null);
    setDuration(0);
    setIsRecording(false);
    setIsPaused(false);
    setAudioExists(false);
    setAudioExpiresAt(null);
    setIsAudioExpired(false);
    setHasBeenTranscribed(false);
    chunksRef.current = [];
    isRecordingRef.current = false;
    isPausedRef.current = false;
    activeSectionRef.current = null;
    retiringSectionRef.current = null;
    forcedSplitInFlightRef.current = false;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    mediaRecorderRef.current = null;
    await teardownVadMonitoring();

    // Clear timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    setIsDeleting(false); // Reset deleting state
  };

  /**
   * Cleanup effect to handle component unmount
   *
   * Ensures timers are cleared and recording is stopped when unmounting
   */
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      clearSectionBoundaryTimers();
      if (vadIntervalRef.current !== null) {
        window.clearInterval(vadIntervalRef.current);
      }
      if (mediaRecorderRef.current?.state !== "inactive") {
        mediaRecorderRef.current?.stop();
      }
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      sourceNodeRef.current?.disconnect();
      analyserRef.current?.disconnect();
      if (
        audioContextRef.current &&
        audioContextRef.current.state !== "closed"
      ) {
        void audioContextRef.current.close();
      }
    };
  }, []);

  return {
    isRecording,
    isPaused,
    duration,
    audioBlob,
    transcriptionDocId: transcriptionDocIdRef.current,
    audioExists,
    recordingSessionId,
    pendingAudioSections,
    audioExpiresAt,
    isAudioExpired,
    isCheckingAudio,
    isDeleting,
    hasBeenTranscribed,
    startRecording,
    stopRecording,
    pauseResumeRecording,
    deleteRecording,
  };
};
