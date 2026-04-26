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
import axiosInstance from "@/commons/utils/axiosInstance";
import { logger } from "@/lib/logger";

const SECTION_DURATION_MS = 15000;
const SECTION_OVERLAP_MS = 2000;
const MEDIA_RECORDER_TIMESLICE_MS = 100;

type TimedChunk = {
  blob: Blob;
  offsetMs: number;
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
      `/api/v1/encounters/${encounterId}/audio/exists`
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
  transcriptionDocId?: number
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
  const [recordingSessionId, setRecordingSessionId] = useState<string | null>(null);
  const [pendingAudioSections, setPendingAudioSections] = useState(0);

  // Refs for managing media recorder and timer
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sectionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timedChunksRef = useRef<TimedChunk[]>([]);
  const recordingStartedAtRef = useRef<number>(0);
  const nextSectionIndexRef = useRef(0);
  const lastSectionEndMsRef = useRef(0);
  const lastEmittedSectionEndMsRef = useRef(0);
  const recordingSessionIdRef = useRef<string | null>(null);

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
      `[VOICE_RECORDER] Effect running for encounterId: ${encounterId}. Resetting state.`
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
    timedChunksRef.current = [];
    nextSectionIndexRef.current = 0;
    lastSectionEndMsRef.current = 0;
    lastEmittedSectionEndMsRef.current = 0;
    recordingSessionIdRef.current = null;
    setRecordingSessionId(null);
    setPendingAudioSections(0);
    if (timerRef.current) clearInterval(timerRef.current);
    if (sectionTimerRef.current) clearTimeout(sectionTimerRef.current);
    timerRef.current = null;
    sectionTimerRef.current = null;

    // Stop any active recorder
    if (mediaRecorderRef.current?.state !== "inactive") {
      try {
        mediaRecorderRef.current?.stop();
      } catch (e) {
        logger.warn("Error stopping previous recorder:", e);
      }
    }
    mediaRecorderRef.current = null;

    const checkExistingAudio = async () => {
      if (encounterId > 0) {
        setIsCheckingAudio(true);
        logger.debug(
          `[VOICE_RECORDER] Checking audio for encounter ${encounterId}`
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
            { exists, existingDuration, has_been_transcribed, expires_at, is_expired }
          );

          setAudioExists(exists);
          setDuration(exists ? existingDuration : 0);
          setAudioExpiresAt(exists ? expires_at : null);
          setIsAudioExpired(exists ? is_expired : false);
          setHasBeenTranscribed(exists ? has_been_transcribed : false);
        } catch (error) {
          logger.error(
            `[VOICE_RECORDER] Error checking audio for ${encounterId}:`,
            error
          );
          setAudioExists(false);
          setDuration(0);
          setAudioExpiresAt(null);
          setIsAudioExpired(false);
          setHasBeenTranscribed(false);
        } finally {
          setIsCheckingAudio(false);
          logger.debug(
            `[VOICE_RECORDER] Finished checking audio for ${encounterId}`
          );
        }
      } else {
        logger.debug(
          `[VOICE_RECORDER] Invalid encounterId (${encounterId}), skipping check.`
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
        `[VOICE_RECORDER] Cleanup effect for encounter ${encounterId}`
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

  const processPendingSections = async () => {
    const sections = await listPendingSections(encounterId);
    setPendingAudioSections(sections.length);

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
              section.content_type
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
            section.content_type
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
          }
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
      } catch (error) {
        logger.error("[VOICE_RECORDER] Error processing pending section:", error);
        await updateLocalSection(section.local_section_id, {
          status: "failed_retryable",
        });
      }
    }

    await refreshPendingSectionCount();
  };

  useEffect(() => {
    void processPendingSections();
    const handleOnline = () => {
      void processPendingSections();
    };
    window.addEventListener("online", handleOnline);
    return () => window.removeEventListener("online", handleOnline);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [encounterId]);

  const saveSectionFromChunks = async (endTimeMs: number, isFinal = false) => {
    const activeSessionId = recordingSessionIdRef.current;
    const documentId = transcriptionDocIdRef.current;
    if (!activeSessionId || !documentId || timedChunksRef.current.length === 0) {
      return;
    }

    const sectionIndex = nextSectionIndexRef.current;
    const overlapMs = sectionIndex === 0 ? 0 : SECTION_OVERLAP_MS;
    const startTimeMs =
      sectionIndex === 0
        ? 0
        : Math.max(
            lastEmittedSectionEndMsRef.current - SECTION_OVERLAP_MS,
            endTimeMs - SECTION_DURATION_MS
          );
    if (!isFinal && endTimeMs - lastSectionEndMsRef.current < SECTION_DURATION_MS) {
      return;
    }
    if (isFinal && endTimeMs - lastEmittedSectionEndMsRef.current < 1000) {
      return;
    }

    const sectionChunks = timedChunksRef.current.filter(
      (chunk) => chunk.offsetMs >= startTimeMs && chunk.offsetMs <= endTimeMs
    );
    if (sectionChunks.length === 0) {
      return;
    }

    const contentType = mediaRecorderRef.current?.mimeType || "audio/webm";
    const localSectionId = crypto.randomUUID();
    const now = new Date().toISOString();
    const localSection: LocalAudioSection = {
      local_section_id: localSectionId,
      recording_session_id: activeSessionId,
      encounter_id: encounterId,
      document_id: documentId,
      section_index: sectionIndex,
      start_time_ms: startTimeMs,
      end_time_ms: endTimeMs,
      overlap_ms: overlapMs,
      blob: new Blob(
        sectionChunks.map((chunk) => chunk.blob),
        { type: contentType }
      ),
      content_type: contentType,
      status: "recorded",
      retry_count: 0,
      created_at: now,
      updated_at: now,
    };

    await saveLocalSection(localSection);
    nextSectionIndexRef.current += 1;
    lastEmittedSectionEndMsRef.current = endTimeMs;
    lastSectionEndMsRef.current = isFinal
      ? endTimeMs
      : Math.max(0, endTimeMs - SECTION_OVERLAP_MS);
    timedChunksRef.current = timedChunksRef.current.filter(
      (chunk) => chunk.offsetMs >= lastSectionEndMsRef.current - SECTION_OVERLAP_MS
    );
    await processPendingSections();
  };

  const scheduleNextSectionFlush = () => {
    if (sectionTimerRef.current) clearTimeout(sectionTimerRef.current);
    sectionTimerRef.current = setTimeout(() => {
      const elapsedMs = Date.now() - recordingStartedAtRef.current;
      void saveSectionFromChunks(elapsedMs).finally(scheduleNextSectionFlush);
    }, nextSectionIndexRef.current === 0 ? SECTION_DURATION_MS : SECTION_DURATION_MS - SECTION_OVERLAP_MS);
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
          transcriptionDocIdRef.current
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
      const stream = await navigator.mediaDevices.getUserMedia(
        audioConstraints
      );

      // 3. Find best supported audio format
      const supportedType = getBestSupportedAudioType();

      // 4. Create MediaRecorder with optimized settings
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: supportedType,
        audioBitsPerSecond: 24000, // Lower bitrate for smaller files
      });

      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];
      timedChunksRef.current = [];
      recordingStartedAtRef.current = Date.now();
      nextSectionIndexRef.current = 0;
      lastSectionEndMsRef.current = 0;
      lastEmittedSectionEndMsRef.current = 0;

      mediaRecorder.ondataavailable = (e) => {
        const elapsedMs = Date.now() - recordingStartedAtRef.current;
        chunksRef.current.push(e.data);
        if (e.data.size > 0) {
          timedChunksRef.current.push({ blob: e.data, offsetMs: elapsedMs });
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(chunksRef.current, {
          type: mediaRecorderRef.current?.mimeType || "audio/webm",
        });

        // Log file size information
        const fileSizeKB = audioBlob.size / 1024;
        logger.debug(
          `[VOICE_RECORDER] Recording complete: ${fileSizeKB.toFixed(
            2
          )} KB, ${duration} seconds`
        );

        setAudioBlob(audioBlob);
        setAudioExists(true);
        stream.getTracks().forEach((track) => track.stop());
      };

      // Reset duration if we're starting a new recording
      if (audioExists) {
        setDuration(0);
        setAudioExpiresAt(null);
        setIsAudioExpired(false);
      }

      mediaRecorder.start(MEDIA_RECORDER_TIMESLICE_MS);
      setIsRecording(true);
      setIsPaused(false);
      timerRef.current = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
      scheduleNextSectionFlush();
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
    if (!mediaRecorderRef.current || !isRecording) return;

    try {
      if (isPaused) {
        // Resume recording
        mediaRecorderRef.current.resume();
        timerRef.current = setInterval(() => {
          setDuration((prev) => prev + 1);
        }, 1000);
        scheduleNextSectionFlush();
        setIsPaused(false);
      } else {
        // Pause recording
        mediaRecorderRef.current.pause();
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
        if (sectionTimerRef.current) {
          clearTimeout(sectionTimerRef.current);
          sectionTimerRef.current = null;
        }
        setIsPaused(true);
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
    if (mediaRecorderRef.current) {
      // If paused, we need to resume first before stopping
      if (isPaused && mediaRecorderRef.current.state === "paused") {
        try {
          mediaRecorderRef.current.resume();
        } catch (error) {
          logger.error("Error resuming recording before stop:", error);
        }
      }

      // Now stop the recording
      try {
        mediaRecorderRef.current.stop();
        if (sectionTimerRef.current) {
          clearTimeout(sectionTimerRef.current);
          sectionTimerRef.current = null;
        }

        // Give time for the onstop handler to execute and set the audioBlob
        setTimeout(async () => {
          const elapsedMs = Date.now() - recordingStartedAtRef.current;
          await saveSectionFromChunks(elapsedMs, true);
          if (recordingSessionIdRef.current) {
            await finishRecordingSession(recordingSessionIdRef.current);
          }

          // Generate upload URL if we have a transcription document ID
          if (transcriptionDocIdRef.current && !recordingSessionIdRef.current) {
            try {
              if (!encounterId || encounterId <= 0) {
                logger.error(
                  "[VOICE_RECORDER] Invalid encounterId in stopRecording:",
                  encounterId
                );
                return;
              }
              const uploadUrl = await generateAudioUploadUrl(
                encounterId,
                duration
              );

              if (!uploadUrl) {
                logger.error("[VOICE_RECORDER] Failed to get upload URL");
                return;
              }

              // Get the current audio blob
              const currentAudioBlob =
                chunksRef.current.length > 0
                  ? new Blob(chunksRef.current, {
                      type: mediaRecorderRef.current?.mimeType || "audio/webm",
                    })
                  : null;

              if (currentAudioBlob) {
                // Upload using the dedicated function
                const uploadSuccess = await uploadAudioToCloud(
                  currentAudioBlob,
                  uploadUrl,
                  mediaRecorderRef.current?.mimeType || "audio/webm"
                );

                if (!uploadSuccess) {
                  logger.error(
                    "[VOICE_RECORDER] Failed to upload audio recording"
                  );
                } else {
                  setIsAudioExpired(false);
                  setAudioExpiresAt(null);
                }
              } else {
                logger.error(
                  "[VOICE_RECORDER] No audio data available to upload"
                );
              }
            } catch (error) {
              logger.error(
                "[VOICE_RECORDER] Error during upload process:",
                error
              );
            }
          } else {
            logger.debug(
              "[VOICE_RECORDER] No transcription document ID provided, skipping upload"
            );
          }
        }, 300); // Small delay to ensure onstop has executed
      } catch (error) {
        logger.error("Error stopping recording:", error);
      }

      // Update states
      setIsRecording(false);
      setIsPaused(false);

      // Clear timer
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
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
            `[VOICE_RECORDER] Attempting to delete audio for encounter ${encounterId}`
          );
          await axiosInstance.delete(`/api/v1/encounters/${encounterId}/audio`);
          logger.debug(
            "[VOICE_RECORDER] Server delete request sent for encounter",
            encounterId
          );
        } else {
          logger.warn(
            "[VOICE_RECORDER] Invalid encounterId in deleteRecording:",
            encounterId
          );
        }
      } catch (error) {
        logger.error(
          "[VOICE_RECORDER] Error deleting audio from server:",
          error
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

    // Clear timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (sectionTimerRef.current) {
      clearTimeout(sectionTimerRef.current);
      sectionTimerRef.current = null;
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
      if (sectionTimerRef.current) clearTimeout(sectionTimerRef.current);
      if (mediaRecorderRef.current?.state !== "inactive") {
        mediaRecorderRef.current?.stop();
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
