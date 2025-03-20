import axiosInstance from "@/utils/axiosInstance";

/**
 * Upload audio to cloud storage
 *
 * @param blob - Audio blob to upload
 * @param uploadUrl - Google Cloud Storage signed URL
 * @param contentType - The mime type of the audio
 * @returns Promise resolving to success status
 */
export const uploadAudioToCloud = async (
    blob: Blob,
    uploadUrl: string,
    contentType: string = "audio/webm"
): Promise<boolean> => {
    try {
        console.log(`[VOICE_RECORDER] Starting audio upload to GCS`);
        console.log(
            `[VOICE_RECORDER] Uploading audio with content type: ${contentType}`
        );

        // Use native fetch API instead of axiosInstance
        const uploadResponse = await fetch(uploadUrl, {
            method: "PUT",
            body: blob,
            headers: {
                "Content-Type": contentType,
            },
            // Important! Don't send credentials or CSRF tokens
            credentials: "omit",
            mode: "cors",
        });

        if (uploadResponse.ok) {
            console.log("[VOICE_RECORDER] Audio upload successful");
            return true;
        } else {
            console.error(
                `[VOICE_RECORDER] Upload failed with status: ${uploadResponse.status} ${uploadResponse.statusText}`
            );
            return false;
        }
    } catch (error) {
        console.error("[VOICE_RECORDER] Exception during GCS upload:", error);
        return false;
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
        console.log(
            `[VOICE_RECORDER] Generating upload URL for encounter ${encounterId} with duration ${audioDurationSeconds}s`
        );

        const response = await axiosInstance.post(
            `/api/generar_url_audio/${encounterId}`,
            { audio_duration_seconds: audioDurationSeconds }
        );

        console.log(`[VOICE_RECORDER] Upload URL generated successfully`);
        return response.data.upload_url;
    } catch (error) {
        console.error("[VOICE_RECORDER] Failed to generate upload URL:", error);
        return null;
    }
};
