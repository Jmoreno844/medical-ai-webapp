import { SpanKind, trace } from "@opentelemetry/api";
import axios from "axios";
import axiosInstance from "@/commons/utils/axiosInstance";
import type {
  ChunkTranscript,
  TranscriptionTurn,
} from "@/types/transcription";
import { logger } from "@/lib/logger";

const tracer = trace.getTracer("vexthealth-webapp");

const getApiErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (data && typeof data === "object") {
      const payload = data as { error?: unknown; detail?: unknown; message?: unknown };
      const message = payload.error ?? payload.detail ?? payload.message;
      if (typeof message === "string" && message.trim()) {
        return message;
      }
    }
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
};

/**
 * Upload audio to cloud storage
 *
 * @param blob - Audio blob to upload|
 * @param uploadUrl - Google Cloud Storage signed URL
 * @param contentType - The mime type of the audio
 * @returns Promise resolving to success status
 */
export const uploadAudioToCloud = async (
  blob: Blob,
  uploadUrl: string,
  contentType: string = "audio/webm"
): Promise<boolean> => {
  const span = tracer.startSpan("gcs.signed_url_upload", {
    kind: SpanKind.CLIENT,
  });
  span.setAttribute("gcs.upload.content_type", contentType);

  try {
    logger.debug(`[VOICE_RECORDER] Starting audio upload to GCS`);
    logger.debug(
      `[VOICE_RECORDER] Uploading audio with content type: ${contentType}`
    );

    const uploadResponse = await fetch(uploadUrl, {
      method: "PUT",
      body: blob,
      headers: {
        "Content-Type": contentType,
      },
      credentials: "omit",
      mode: "cors",
    });

    span.setAttribute("http.response.status_code", uploadResponse.status);

    if (uploadResponse.ok) {
      logger.debug("[VOICE_RECORDER] Audio upload successful");
      return true;
    }
    logger.error(
      `[VOICE_RECORDER] Upload failed with status: ${uploadResponse.status} ${uploadResponse.statusText}`
    );
    return false;
  } catch (error) {
    if (error instanceof Error) {
      span.recordException(error);
    } else {
      span.recordException(new Error(String(error)));
    }
    logger.error("[VOICE_RECORDER] Exception during GCS upload:", error);
    return false;
  } finally {
    span.end();
  }
};

/**
 * Generates a signed URL for audio upload
 *
 * @param encounterId - The ID of the encounter
 * @param audioDurationSeconds - Duration of the audio in seconds
 * @returns Promise resolving to the signed URL
 */
export const generateAudioUploadUrl = async (
  encounterId: number,
  audioDurationSeconds: number
): Promise<string | null> => {
  try {
    logger.debug(
      `[VOICE_RECORDER] Generating upload URL for encounter ${encounterId} with duration ${audioDurationSeconds}s`
    );

    const response = await axiosInstance.post(
      `/api/v1/encounters/${encounterId}/audio/upload-url`,
      { audio_duration_seconds: audioDurationSeconds }
    );

    logger.debug(
      "[VOICE_RECORDER] Upload URL generated (has_url=%s)",
      Boolean(response.data?.upload_url)
    );
    return response.data.upload_url;
  } catch (error) {
    logger.error("[VOICE_RECORDER] Failed to generate upload URL:", error);
    return null;
  }
};

export const createRecordingSession = async (
  encounterId: number,
  documentId: number
): Promise<string | null> => {
  try {
    const response = await axiosInstance.post(`/api/v1/transcription/sessions`, {
      encounter_id: encounterId,
      document_id: documentId,
    });
    return response.data?.session_id ?? null;
  } catch (error) {
    logger.error("[VOICE_RECORDER] Failed to create recording session:", error);
    return null;
  }
};

export type RecordingSessionSection = {
  section_id: string;
  client_section_id: string;
  section_index: number;
  start_time_ms: number;
  end_time_ms: number;
  overlap_ms: number;
  gcs_object_name: string;
  content_type: string;
  byte_size?: number | null;
  status: string;
  turns?: TranscriptionTurn[] | null;
  raw_transcript?: string | null;
  error_code?: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
};

export type RecordingSessionStatus = {
  success: boolean;
  session_id: string;
  encounter_id: number;
  document_id: number;
  status: string;
  started_at: string;
  finished_at?: string | null;
  finalized_at?: string | null;
  consolidated_transcript?: string | null;
  chunks?: ChunkTranscript[];
  error_code?: string | null;
  sections: RecordingSessionSection[];
};

const RECORDING_SECTION_COMPLETE_STATUSES = new Set([
  "transcribed",
  "discarded_no_speech",
]);

export function areAllRecordingSectionsComplete(
  sections: RecordingSessionSection[],
): boolean {
  return (
    sections.length > 0 &&
    sections.every((section) =>
      RECORDING_SECTION_COMPLETE_STATUSES.has(section.status),
    )
  );
}

export function resolveRecordingSessionIdsToFinishWhenDrained(
  processedSessionIds: Iterable<string>,
  activeRecordingSessionId: string | null,
  remainingPendingSectionCount: number,
  finishSessionsWhenDrained: boolean,
): string[] {
  if (!finishSessionsWhenDrained || remainingPendingSectionCount > 0) {
    return [];
  }

  const sessionIds = new Set(processedSessionIds);
  if (activeRecordingSessionId) {
    sessionIds.add(activeRecordingSessionId);
  }

  return Array.from(sessionIds);
}

export const generateSectionUploadUrl = async (
  recordingSessionId: string,
  clientSectionId: string,
  sectionIndex: number,
  contentTypeOriginal: string,
  contentTypeClipped: string,
): Promise<{
  original: { uploadUrl: string; gcsObjectName: string; contentType: string };
  clipped: { uploadUrl: string; gcsObjectName: string; contentType: string };
} | null> => {
  try {
    const response = await axiosInstance.post(
      `/api/v1/transcription/sessions/${recordingSessionId}/sections/upload-url`,
      {
        client_section_id: clientSectionId,
        section_index: sectionIndex,
        content_type_original: contentTypeOriginal,
        content_type_clipped: contentTypeClipped,
      }
    );
    if (!response.data?.success) {
      logger.error(
        "[VOICE_RECORDER] Failed to generate section upload URL:",
        response.data?.error || "Unknown API error"
      );
      return null;
    }
    return {
      original: {
        uploadUrl: response.data.original.upload_url,
        gcsObjectName: response.data.original.gcs_object_name,
        contentType: response.data.original.content_type,
      },
      clipped: {
        uploadUrl: response.data.clipped.upload_url,
        gcsObjectName: response.data.clipped.gcs_object_name,
        contentType: response.data.clipped.content_type,
      },
    };
  } catch (error) {
    logger.error(
      "[VOICE_RECORDER] Failed to generate section upload URL:",
      getApiErrorMessage(error)
    );
    return null;
  }
};

export const registerAudioSection = async (
  recordingSessionId: string,
  payload: {
    client_section_id: string;
    section_index: number;
    start_time_ms: number;
    end_time_ms: number;
    overlap_ms: number;
    original_gcs_object_name: string;
    original_content_type: string;
    original_byte_size?: number;
    clipped_gcs_object_name: string;
    clipped_content_type: string;
    clipped_byte_size?: number;
    transcription_source_gcs_object_name: string;
    frontend_vad_metadata?: Record<string, unknown>;
  }
): Promise<{ success: boolean; backendSectionId?: string }> => {
  try {
    const response = await axiosInstance.post(
      `/api/v1/transcription/sessions/${recordingSessionId}/sections`,
      payload
    );
    return {
      success: response.data?.success === true,
      backendSectionId: response.data?.section?.section_id,
    };
  } catch (error) {
    logger.error("[VOICE_RECORDER] Failed to register audio section:", error);
    return { success: false };
  }
};

export const retryTranscriptionSession = async (
  recordingSessionId: string,
): Promise<{
  success: boolean;
  status?: string;
  error?: string;
  error_code?: string;
}> => {
  try {
    const response = await axiosInstance.post(
      `/api/v1/transcription/sessions/${recordingSessionId}/retry`,
    );
    return {
      success: response.data?.success === true,
      status: response.data?.status,
      error: response.data?.error,
      error_code: response.data?.error_code,
    };
  } catch (error) {
    logger.error(
      "[VOICE_RECORDER] Failed to retry transcription session:",
      error,
    );
    return {
      success: false,
      error: getApiErrorMessage(error),
    };
  }
};

export const finishRecordingSession = async (
  recordingSessionId: string
): Promise<boolean> => {
  try {
    const response = await axiosInstance.post(
      `/api/v1/transcription/sessions/${recordingSessionId}/finish`
    );
    return response.data?.success === true;
  } catch (error) {
    logger.error("[VOICE_RECORDER] Failed to finish recording session:", error);
    return false;
  }
};

export const getRecordingSessionStatus = async (
  recordingSessionId: string
): Promise<RecordingSessionStatus | null> => {
  try {
    const response = await axiosInstance.get(
      `/api/v1/transcription/sessions/${recordingSessionId}`
    );
    if (response.data?.success !== true) {
      logger.warn("[VOICE_RECORDER] Recording session status not successful", {
        recordingSessionId,
        status: response.data?.status,
      });
      return null;
    }
    return response.data as RecordingSessionStatus;
  } catch (error) {
    logger.error(
      "[VOICE_RECORDER] Failed to fetch recording session status:",
      getApiErrorMessage(error)
    );
    return null;
  }
};

export const getRecordingSessionStatusForDocument = async (
  documentId: number
): Promise<RecordingSessionStatus | null> => {
  try {
    const response = await axiosInstance.get(
      `/api/v1/transcription/documents/${documentId}/session`
    );
    if (response.data?.success !== true) {
      logger.warn("[VOICE_RECORDER] Document recording session status not successful", {
        documentId,
        status: response.data?.status,
      });
      return null;
    }
    return response.data as RecordingSessionStatus;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null;
    }
    logger.error(
      "[VOICE_RECORDER] Failed to fetch recording session status for document:",
      getApiErrorMessage(error)
    );
    return null;
  }
};
