import { useState, useEffect, useRef } from "react";
import { UseVoiceRecorderReturn } from "./types";
import { getBestSupportedAudioType } from "./utils";
import { uploadAudioToCloud, generateAudioUploadUrl } from "./uploadService";

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
    transcriptionDocId?: number
): UseVoiceRecorderReturn => {
    // State for recording status
    const [isRecording, setIsRecording] = useState(false);
    const [isPaused, setIsPaused] = useState(false);
    const [duration, setDuration] = useState(0);
    const [audioBlob, setAudioBlob] = useState<Blob | null>(null);

    // Refs for managing media recorder and timer
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const timerRef = useRef<NodeJS.Timeout | null>(null);
    const chunksRef = useRef<Blob[]>([]);

    // Store the transcription document ID
    const transcriptionDocIdRef = useRef<number | undefined>(
        transcriptionDocId
    );

    // Update ref when prop changes
    useEffect(() => {
        transcriptionDocIdRef.current = transcriptionDocId;
    }, [transcriptionDocId]);

    /**
     * Start recording audio
     */
    const startRecording = async () => {
        try {
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

            mediaRecorder.ondataavailable = (e) => {
                chunksRef.current.push(e.data);
            };

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(chunksRef.current, {
                    type: mediaRecorderRef.current?.mimeType || "audio/webm",
                });

                // Log file size information
                const fileSizeKB = audioBlob.size / 1024;
                console.log(
                    `[VOICE_RECORDER] Recording complete: ${fileSizeKB.toFixed(
                        2
                    )} KB, ${duration} seconds`
                );

                setAudioBlob(audioBlob);
                stream.getTracks().forEach((track) => track.stop());
            };

            mediaRecorder.start(100); // Collect chunks every 100ms for smoother pausing
            setIsRecording(true);
            setIsPaused(false);
            setDuration(0);
            timerRef.current = setInterval(() => {
                setDuration((prev) => prev + 1);
            }, 1000);
        } catch (error) {
            console.error("Error starting recording:", error);
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
                setIsPaused(false);
            } else {
                // Pause recording
                mediaRecorderRef.current.pause();
                if (timerRef.current) {
                    clearInterval(timerRef.current);
                    timerRef.current = null;
                }
                setIsPaused(true);
            }
        } catch (error) {
            console.error("Error pausing/resuming recording:", error);
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
                    console.error(
                        "Error resuming recording before stop:",
                        error
                    );
                }
            }

            // Now stop the recording
            try {
                mediaRecorderRef.current.stop();

                // Give time for the onstop handler to execute and set the audioBlob
                setTimeout(async () => {
                    // Generate upload URL if we have a transcription document ID
                    if (transcriptionDocIdRef.current) {
                        try {
                            // Extract encounter ID from URL path
                            const urlParts =
                                typeof window !== "undefined"
                                    ? window.location.pathname.split("/")
                                    : [];
                            const encounterIdFromUrl =
                                parseInt(urlParts[urlParts.length - 1]) || 0;

                            // Get upload URL - now passing duration
                            const uploadUrl = await generateAudioUploadUrl(
                                encounterIdFromUrl,
                                duration
                            );

                            if (!uploadUrl) {
                                console.error(
                                    "[VOICE_RECORDER] Failed to get upload URL"
                                );
                                return;
                            }

                            // Get the current audio blob
                            const currentAudioBlob =
                                chunksRef.current.length > 0
                                    ? new Blob(chunksRef.current, {
                                          type:
                                              mediaRecorderRef.current
                                                  ?.mimeType || "audio/webm",
                                      })
                                    : null;

                            if (currentAudioBlob) {
                                // Upload using the dedicated function
                                const uploadSuccess = await uploadAudioToCloud(
                                    currentAudioBlob,
                                    uploadUrl,
                                    mediaRecorderRef.current?.mimeType ||
                                        "audio/webm"
                                );

                                if (!uploadSuccess) {
                                    console.error(
                                        "[VOICE_RECORDER] Failed to upload audio recording"
                                    );
                                }
                            } else {
                                console.error(
                                    "[VOICE_RECORDER] No audio data available to upload"
                                );
                            }
                        } catch (error) {
                            console.error(
                                "[VOICE_RECORDER] Error during upload process:",
                                error
                            );
                        }
                    } else {
                        console.log(
                            "[VOICE_RECORDER] No transcription document ID provided, skipping upload"
                        );
                    }
                }, 300); // Small delay to ensure onstop has executed
            } catch (error) {
                console.error("Error stopping recording:", error);
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
     */
    const deleteRecording = () => {
        if (mediaRecorderRef.current?.state !== "inactive") {
            try {
                mediaRecorderRef.current?.stop();
            } catch (error) {
                console.error(
                    "Error stopping recorder during deletion:",
                    error
                );
            }
        }

        // Reset all states
        setAudioBlob(null);
        setDuration(0);
        setIsRecording(false);
        setIsPaused(false);
        chunksRef.current = [];

        // Clear timer
        if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }
    };

    /**
     * Cleanup effect to handle component unmount
     *
     * Ensures timers are cleared and recording is stopped when unmounting
     */
    useEffect(() => {
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
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
        startRecording,
        stopRecording,
        pauseResumeRecording,
        deleteRecording,
    };
};
