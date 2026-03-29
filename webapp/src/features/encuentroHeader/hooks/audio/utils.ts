import { logger } from "@/lib/logger";
/**
 * Formats seconds to mm:ss time format
 *
 * @param seconds - Number of seconds to format
 * @returns Formatted time string in mm:ss format
 */
export const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs
        .toString()
        .padStart(2, "0")}`;
};

/**
 * Determines the best supported audio mime type for recording
 * @returns The best supported mime type or fallback
 */
export const getBestSupportedAudioType = (): string => {
    // Order by efficiency for voice recording
    const mimeTypes = [
        "audio/webm;codecs=opus", // Most efficient for voice
        "audio/ogg;codecs=opus", // Alternative codec
        "audio/webm", // Fallback
    ];

    const supportedType = mimeTypes.find((type) =>
        MediaRecorder.isTypeSupported(type)
    );

    logger.debug(
        `[VOICE_RECORDER] Using audio format: ${supportedType || "default"}`
    );

    return supportedType || "audio/webm";
};
