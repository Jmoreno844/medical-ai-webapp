import { SpanKind, trace } from "@opentelemetry/api";
import axiosInstance from "@/commons/utils/axiosInstance";
import { logger } from "@/lib/logger";

const tracer = trace.getTracer("vexthealth-webapp");

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

export const generateSectionUploadUrl = async (
  recordingSessionId: string,
  clientSectionId: string,
  sectionIndex: number,
  contentType: string
): Promise<{ uploadUrl: string; gcsObjectName: string } | null> => {
  try {
    const response = await axiosInstance.post(
      `/api/v1/transcription/sessions/${recordingSessionId}/sections/upload-url`,
      {
        client_section_id: clientSectionId,
        section_index: sectionIndex,
        content_type: contentType,
      }
    );
    if (!response.data?.success) return null;
    return {
      uploadUrl: response.data.upload_url,
      gcsObjectName: response.data.gcs_object_name,
    };
  } catch (error) {
    logger.error("[VOICE_RECORDER] Failed to generate section upload URL:", error);
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
    gcs_object_name: string;
    content_type: string;
    byte_size?: number;
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
