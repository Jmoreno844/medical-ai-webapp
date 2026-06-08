import { useCallback, useEffect, useRef, useState } from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import {
  AudioRecorderController,
  type LiveRecordingState,
  type RecordedSection,
} from "@/audio/recording/AudioRecorderController";
import { prepareRecordedSectionArtifacts } from "@/audio/recording/postRecordingAudioPipeline";
import { SEGMENTATION_CONFIG } from "@/audio/segmentation/segmentationConfig";
import { logger } from "@/lib/logger";
import { getStoredMicrophoneDeviceId } from "./useMicrophoneDevices";
import {
  createRecordingSession,
  finishRecordingSession,
  generateSectionUploadUrl,
  getRecordingSessionStatus,
  registerAudioSection,
  uploadAudioToCloud,
} from "./uploadService";
import {
  deleteLocalSectionBlob,
  listPendingSections,
  saveLocalSection,
  updateLocalSection,
  type LocalAudioSection,
} from "./sectionQueue";
import { UseVoiceRecorderReturn } from "./types";

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

const checkAudioExists = async (encounterId: number) => {
  try {
    const response = await axiosInstance.get(
      `/api/v1/encounters/${encounterId}/audio/exists`,
    );
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

const getPendingSectionsDurationSeconds = (
  sections: LocalAudioSection[],
): number => {
  const maxEndTimeMs = sections.reduce(
    (maxEndTime, section) => Math.max(maxEndTime, section.end_time_ms ?? 0),
    0,
  );
  return Math.ceil(maxEndTimeMs / 1000);
};

const uploadOriginalAudioEnabled =
  (import.meta.env.VITE_UPLOAD_ORIGINAL_AUDIO_ENABLED ?? "true") !== "false";

const getNextSectionIndex = async (
  encounterId: number,
  recordingSessionId: string,
): Promise<number> => {
  const [pendingSections, sessionStatus] = await Promise.all([
    listPendingSections(encounterId),
    getRecordingSessionStatus(recordingSessionId),
  ]);

  const highestPendingIndex = pendingSections
    .filter((section) => section.recording_session_id === recordingSessionId)
    .reduce(
      (highestIndex, section) => Math.max(highestIndex, section.section_index),
      -1,
    );
  const highestRegisteredIndex = (sessionStatus?.sections ?? []).reduce(
    (highestIndex, section) => Math.max(highestIndex, section.section_index),
    -1,
  );

  return Math.max(highestPendingIndex, highestRegisteredIndex) + 1;
};

export const useVoiceRecorder = (
  encounterId: number,
  transcriptionDocId?: number,
): UseVoiceRecorderReturn => {
  const [liveState, setLiveState] = useState<LiveRecordingState>(INITIAL_LIVE_STATE);
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

  const controllerRef = useRef<AudioRecorderController | null>(null);
  const recordingSessionIdRef = useRef<string | null>(null);
  const nextSectionIndexRef = useRef(0);
  const isStoppingRef = useRef(false);
  const transcriptionDocIdRef = useRef<number | undefined>(transcriptionDocId);
  const liveStateRef = useRef(INITIAL_LIVE_STATE);
  const sectionProcessingChainRef = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    transcriptionDocIdRef.current = transcriptionDocId;
  }, [transcriptionDocId]);

  const refreshPendingSectionCount = useCallback(async () => {
    const sections = await listPendingSections(encounterId);
    setPendingAudioSections(sections.length);
    if (sections.length > 0) {
      setAudioExists(true);
      setDuration((current) =>
        Math.max(current, getPendingSectionsDurationSeconds(sections)),
      );
    }
  }, [encounterId]);

  const processPendingSections = useCallback(
    async ({
      finishSessionsWhenDrained = false,
    }: { finishSessionsWhenDrained?: boolean } = {}) => {
      const sections = await listPendingSections(encounterId);
      setPendingAudioSections(sections.length);
      const processedSessionIds = new Set<string>();

      for (const section of sections) {
        if (!section.clipped_blob || (!section.original_blob && uploadOriginalAudioEnabled)) {
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
            Boolean(section.original_gcs_object_name) &&
            Boolean(section.clipped_gcs_object_name) &&
            ["uploaded", "registering"].includes(section.status);
          const uploadInfo = alreadyUploaded
            ? {
                original: {
                  uploadUrl: "",
                  gcsObjectName: section.original_gcs_object_name as string,
                  contentType: section.original_content_type,
                },
                clipped: {
                  uploadUrl: "",
                  gcsObjectName: section.clipped_gcs_object_name as string,
                  contentType: section.clipped_content_type,
                },
              }
            : await generateSectionUploadUrl(
                section.recording_session_id,
                section.local_section_id,
                section.section_index,
                section.original_content_type,
                section.clipped_content_type,
              );

          if (!uploadInfo) {
            await updateLocalSection(section.local_section_id, {
              status: "failed_retryable",
            });
            continue;
          }

          let originalGcsObjectName = uploadInfo.original.gcsObjectName;
          let clippedGcsObjectName = uploadInfo.clipped.gcsObjectName;
          if (!alreadyUploaded) {
            await updateLocalSection(section.local_section_id, {
              status: "uploading",
              original_gcs_object_name: originalGcsObjectName,
              clipped_gcs_object_name: clippedGcsObjectName,
              transcription_source_gcs_object_name: clippedGcsObjectName,
            });
            if (uploadOriginalAudioEnabled && section.original_blob) {
              const originalUploadSuccess = await uploadAudioToCloud(
                section.original_blob,
                uploadInfo.original.uploadUrl,
                section.original_content_type,
              );
              if (!originalUploadSuccess) {
                await updateLocalSection(section.local_section_id, {
                  status: "failed_retryable",
                });
                continue;
              }
            }
            const clippedUploadSuccess = await uploadAudioToCloud(
              section.clipped_blob,
              uploadInfo.clipped.uploadUrl,
              section.clipped_content_type,
            );
            if (!clippedUploadSuccess) {
              await updateLocalSection(section.local_section_id, {
                status: "failed_retryable",
              });
              continue;
            }
            await updateLocalSection(section.local_section_id, {
              status: "uploaded",
              original_gcs_object_name: originalGcsObjectName,
              clipped_gcs_object_name: clippedGcsObjectName,
              transcription_source_gcs_object_name: clippedGcsObjectName,
            });
          } else {
            originalGcsObjectName = section.original_gcs_object_name as string;
            clippedGcsObjectName = section.clipped_gcs_object_name as string;
          }

          await updateLocalSection(section.local_section_id, {
            status: "registering",
            original_gcs_object_name: originalGcsObjectName,
            clipped_gcs_object_name: clippedGcsObjectName,
            transcription_source_gcs_object_name: clippedGcsObjectName,
          });
          const registerResult = await registerAudioSection(
            section.recording_session_id,
            {
              client_section_id: section.local_section_id,
              section_index: section.section_index,
              start_time_ms: section.start_time_ms,
              end_time_ms: section.end_time_ms,
              overlap_ms: section.overlap_ms,
              original_gcs_object_name: originalGcsObjectName,
              original_content_type: section.original_content_type,
              original_byte_size: section.original_blob?.size,
              clipped_gcs_object_name: clippedGcsObjectName,
              clipped_content_type: section.clipped_content_type,
              clipped_byte_size: section.clipped_blob.size,
              transcription_source_gcs_object_name: clippedGcsObjectName,
              frontend_vad_metadata: section.frontend_vad_metadata,
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
          logger.error("[VOICE_RECORDER] Error processing pending section:", error);
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
    },
    [encounterId, refreshPendingSectionCount],
  );

  const handleRecordedSection = useCallback(
    async (section: RecordedSection) => {
      const activeSessionId = recordingSessionIdRef.current;
      const documentId = transcriptionDocIdRef.current;
      if (!activeSessionId || !documentId || section.blob.size === 0) {
        return;
      }

      const preparedArtifacts = await prepareRecordedSectionArtifacts(
        section.blob,
        section.metadata,
      );

      const now = new Date().toISOString();
      const localSectionId = section.metadata.sectionId;
      const localSection: LocalAudioSection = {
        local_section_id: localSectionId,
        recording_session_id: activeSessionId,
        encounter_id: encounterId,
        document_id: documentId,
        section_index: nextSectionIndexRef.current,
        start_time_ms: Math.round(section.startTimeMs),
        end_time_ms: Math.round(section.endTimeMs),
        overlap_ms: section.metadata.overlapBeforeMs,
        original_blob: preparedArtifacts.originalBlob,
        clipped_blob: preparedArtifacts.clippedBlob,
        original_content_type: preparedArtifacts.originalMimeType,
        clipped_content_type: preparedArtifacts.clippedMimeType,
        status: "recorded",
        retry_count: 0,
        speech_frame_count: Math.max(
          1,
          Math.round(
            preparedArtifacts.normalizedMetadata.speechDurationMs /
              SEGMENTATION_CONFIG.vadFrameDurationMs,
          ),
        ),
        frontend_vad_metadata: {
          ...preparedArtifacts.normalizedMetadata,
          retainedIntervals: preparedArtifacts.retainedIntervals,
        },
        created_at: now,
        updated_at: now,
      };

      await saveLocalSection(localSection);
      nextSectionIndexRef.current += 1;
      setAudioBlob(preparedArtifacts.clippedBlob);
      setAudioExists(true);
      setDuration((current) =>
        Math.max(current, Math.ceil(section.endTimeMs / 1000)),
      );
      await processPendingSections();
    },
    [encounterId, processPendingSections],
  );

  useEffect(() => {
    const controller = new AudioRecorderController();
    controllerRef.current = controller;

    const unsubscribeState = controller.onStateChange((state) => {
      liveStateRef.current = state;
      setLiveState(state);
      setDuration(Math.max(0, Math.ceil(state.wallClockDurationMs / 1000)));
    });
    const unsubscribeSections = controller.onSectionRecorded((section) => {
      sectionProcessingChainRef.current = sectionProcessingChainRef.current
        .then(() => handleRecordedSection(section))
        .catch((error) => {
          logger.error("[VOICE_RECORDER] Failed to persist recorded section:", error);
        });
    });

    return () => {
      unsubscribeState();
      unsubscribeSections();
      void controller.destroy();
      controllerRef.current = null;
    };
  }, [handleRecordedSection]);

  useEffect(() => {
    setLiveState(INITIAL_LIVE_STATE);
    setDuration(0);
    setAudioBlob(null);
    setAudioExists(false);
    setAudioExpiresAt(null);
    setIsAudioExpired(false);
    setHasBeenTranscribed(false);
    setRecordingSessionId(null);
    setPendingAudioSections(0);
    recordingSessionIdRef.current = null;
    nextSectionIndexRef.current = 0;
    isStoppingRef.current = false;

    const checkExistingAudio = async () => {
      if (encounterId <= 0) {
        setIsCheckingAudio(false);
        return;
      }

      setIsCheckingAudio(true);
      try {
        const {
          exists,
          duration: existingDuration,
          has_been_transcribed,
          expires_at,
          is_expired,
        } = await checkAudioExists(encounterId);
        const pendingSections = await listPendingSections(encounterId);
        const pendingSectionsDuration = getPendingSectionsDurationSeconds(
          pendingSections,
        );
        const hasPendingLocalAudio = pendingSections.length > 0;

        setPendingAudioSections(pendingSections.length);
        setAudioExists(exists || hasPendingLocalAudio);
        setDuration(Math.max(existingDuration, pendingSectionsDuration));
        setAudioExpiresAt(exists ? expires_at : null);
        setIsAudioExpired(exists ? is_expired : false);
        setHasBeenTranscribed(exists ? has_been_transcribed : false);
      } catch (error) {
        logger.error(`[VOICE_RECORDER] Error checking audio for ${encounterId}:`, error);
      } finally {
        setIsCheckingAudio(false);
      }
    };

    void checkExistingAudio();

    return () => {
      void controllerRef.current?.destroy();
    };
  }, [encounterId]);

  useEffect(() => {
    void processPendingSections({ finishSessionsWhenDrained: true });
    const handleOnline = () => {
      void processPendingSections({
        finishSessionsWhenDrained: !liveStateRef.current.isRecording,
      });
    };
    window.addEventListener("online", handleOnline);
    return () => window.removeEventListener("online", handleOnline);
  }, [processPendingSections]);

  const startRecording = useCallback(async () => {
    try {
      if (!transcriptionDocIdRef.current) {
        logger.warn(
          "[VOICE_RECORDER] Blocking recording start until transcription document is ready",
        );
        return;
      }

      const nextRecordingSessionId = await createRecordingSession(
        encounterId,
        transcriptionDocIdRef.current,
      );
      if (!nextRecordingSessionId) {
        logger.error("[VOICE_RECORDER] Could not create recording session");
        return;
      }

      recordingSessionIdRef.current = nextRecordingSessionId;
      setRecordingSessionId(nextRecordingSessionId);
      nextSectionIndexRef.current = await getNextSectionIndex(
        encounterId,
        nextRecordingSessionId,
      );

      const preferredDeviceId = getStoredMicrophoneDeviceId();
      const initialElapsedMs =
        audioExists && !isAudioExpired ? duration * 1000 : 0;

      if (isAudioExpired) {
        setDuration(0);
        setAudioExpiresAt(null);
        setIsAudioExpired(false);
      }

      await controllerRef.current?.start({
        preferredDeviceId,
        initialElapsedMs,
      });
    } catch (error) {
      logger.error("[VOICE_RECORDER] Error starting recording:", error);
    }
  }, [audioExists, duration, encounterId, isAudioExpired]);

  const stopRecording = useCallback(async () => {
    if (isStoppingRef.current) {
      return;
    }

    if (!liveStateRef.current.isRecording && !liveStateRef.current.isPaused) {
      return;
    }

    isStoppingRef.current = true;
    try {
      await controllerRef.current?.stop();
      await sectionProcessingChainRef.current;
      await processPendingSections({ finishSessionsWhenDrained: true });
      setAudioExists(true);
    } catch (error) {
      logger.error("[VOICE_RECORDER] Error stopping recording:", error);
    } finally {
      isStoppingRef.current = false;
    }
  }, [processPendingSections]);

  const pauseResumeRecording = useCallback(() => {
    if (liveStateRef.current.isPaused) {
      controllerRef.current?.resume();
      return;
    }
    controllerRef.current?.pause();
  }, []);

  const deleteRecording = useCallback(async () => {
    setIsDeleting(true);
    try {
      await controllerRef.current?.destroy();
      if (audioExists && encounterId > 0) {
        await axiosInstance.delete(`/api/v1/encounters/${encounterId}/audio`);
      }
    } catch (error) {
      logger.error("[VOICE_RECORDER] Error deleting audio:", error);
    } finally {
      setAudioBlob(null);
      setDuration(0);
      setAudioExists(false);
      setAudioExpiresAt(null);
      setIsAudioExpired(false);
      setHasBeenTranscribed(false);
      setRecordingSessionId(null);
      setPendingAudioSections(0);
      recordingSessionIdRef.current = null;
      nextSectionIndexRef.current = 0;
      setIsDeleting(false);
    }
  }, [audioExists, encounterId]);

  return {
    isRecording: liveState.isRecording,
    isPaused: liveState.isPaused,
    duration,
    audioBlob,
    transcriptionDocId,
    audioExists,
    recordingSessionId,
    pendingAudioSections,
    audioExpiresAt,
    isAudioExpired,
    isDeleting,
    hasBeenTranscribed,
    isCheckingAudio,
    startRecording,
    stopRecording: () => {
      void stopRecording();
    },
    pauseResumeRecording,
    deleteRecording,
  };
};
