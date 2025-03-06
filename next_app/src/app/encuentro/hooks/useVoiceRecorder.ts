import { useState, useEffect, useRef } from "react";

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
 * Interface for the return value of useVoiceRecorder hook
 */
interface UseVoiceRecorderReturn {
  isRecording: boolean;
  isPaused: boolean;
  duration: number;
  audioBlob: Blob | null;
  transcriptionDocId?: number;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  pauseResumeRecording: () => void;
  deleteRecording: () => void;
}

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
  const transcriptionDocIdRef = useRef<number | undefined>(transcriptionDocId);

  // Update ref when prop changes
  useEffect(() => {
    transcriptionDocIdRef.current = transcriptionDocId;
  }, [transcriptionDocId]);

  /**
   * Start recording audio
   *
   * Initializes the MediaRecorder, starts collecting audio data,
   * and updates recording state
   */
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
        setAudioBlob(audioBlob);
        stream.getTracks().forEach((track) => track.stop());

        // Here you could implement logic to save the recording to the transcription document
        // if (transcriptionDocIdRef.current) {
        //   saveAudioToTranscriptionDoc(transcriptionDocIdRef.current, audioBlob);
        // }
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
  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      // If paused, we need to resume first before stopping
      if (isPaused && mediaRecorderRef.current.state === "paused") {
        try {
          mediaRecorderRef.current.resume();
        } catch (error) {
          console.error("Error resuming recording before stop:", error);
        }
      }

      // Now stop the recording
      try {
        mediaRecorderRef.current.stop();
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
        console.error("Error stopping recorder during deletion:", error);
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
