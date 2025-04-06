import React, { useEffect, useState, useCallback } from "react";
import { useVoiceRecorder } from "../hooks/audio/useVoiceRecorder";
import TimerDisplay from "./TimerDisplay";
import MicrophoneIcon from "./MicrophoneIcon";
import StartStopButton from "./StartStopButton";
import PauseResumeButton from "./PauseResumeButton";
import DeleteButton from "./DeleteButton";
import SettingsIcon from "./SettingsIcon";
import TranscribeButton from "./TranscribeButton";

// Declare the global cache typing
declare global {
  interface Window {
    documentContentCache?: Map<number, string>;
  }
}

/**
 * Props for the VoiceRecorder component
 */
interface VoiceRecorderProps {
  /** ID of the transcription document if available */
  transcriptionDocId?: number;
  onTranscriptionComplete?: () => void; // Add this prop
  onHasBeenTranscribed?: (value: boolean) => void; // Add this prop
}

/**
 * Voice recorder component with controls
 *
 * Provides UI for recording, pausing, stopping and deleting voice recordings
 *
 * @param props - Component props
 * @returns React component
 */
const VoiceRecorder: React.FC<VoiceRecorderProps> = ({
  transcriptionDocId,
  onTranscriptionComplete,
  onHasBeenTranscribed,
}) => {
  // Use our cleaned up voice recorder hook
  const {
    isRecording,
    isPaused,
    duration,
    audioBlob,
    audioExists,
    isCheckingAudio,
    isDeleting,
    hasBeenTranscribed, // Add this
    startRecording,
    stopRecording,
    pauseResumeRecording,
    deleteRecording,
  } = useVoiceRecorder(transcriptionDocId);

  // UI state management
  const [showPauseButton, setShowPauseButton] = useState(false);
  const [showStartStopButton, setShowStartStopButton] = useState(true);
  const [hasRecordingActivity, setHasRecordingActivity] = useState(false);

  // Add a reset counter to trigger TranscribeButton reset
  const [resetCounter, setResetCounter] = useState(0);

  // Add a tracking state for new transcriptions
  const [_hasNewTranscription, setHasNewTranscription] = useState(false);

  /**
   * Update UI based on recording state
   */
  useEffect(() => {
    // Only show pause button during active recording, hide when stopped
    setShowPauseButton(isRecording);

    // Hide start/stop button only when we have a completed recording
    if (!isRecording && (audioBlob || audioExists)) {
      setShowStartStopButton(false);
    } else {
      setShowStartStopButton(true);
    }

    // If audio exists, we should show the delete button
    if (audioExists && !isCheckingAudio) {
      setHasRecordingActivity(true);
    }
  }, [isRecording, audioBlob, audioExists, isCheckingAudio]);

  // Custom handler for transcription complete that ensures content refresh
  const handleTranscriptionComplete = useCallback(() => {
    console.log(
      "[VOICE_RECORDER] Transcription complete, forcing content refresh"
    );

    // If we have access to the global document cache, clear the entry for this document
    if (window.documentContentCache && transcriptionDocId) {
      console.log(
        `[VOICE_RECORDER] Clearing cache for document ${transcriptionDocId}`
      );
      window.documentContentCache.delete(transcriptionDocId);
    }

    // Set flag to indicate we have a new transcription
    setHasNewTranscription(true);

    // Notify parent of transcription status
    if (onHasBeenTranscribed) {
      onHasBeenTranscribed(true);
    }

    // Call the parent's completion handler
    if (onTranscriptionComplete) {
      onTranscriptionComplete();
    }

    // Reset the flag after a short delay
    setTimeout(() => {
      setHasNewTranscription(false);
    }, 1000);
  }, [transcriptionDocId, onTranscriptionComplete, onHasBeenTranscribed]);

  /**
   * Handle recording start/stop
   */
  const handleStartStop = () => {
    // If recording is active, stop it
    if (isRecording) {
      // If currently paused, resume before stopping to ensure proper cleanup
      if (isPaused) {
        pauseResumeRecording(); // Resume first
      }
      stopRecording(); // Then stop
      setHasRecordingActivity(true);
    }
    // If not recording, start a new recording
    else {
      startRecording();
      setHasRecordingActivity(true);
    }
  };

  /**
   * Custom delete handler to reset all states
   */
  const handleDelete = () => {
    // First capture was recording/paused state before deletion

    // Call the hook's delete function
    deleteRecording();

    // Reset the new transcription flag
    setHasNewTranscription(false);

    // Notify parent when audio is deleted
    if (onHasBeenTranscribed) {
      onHasBeenTranscribed(false);
    }

    // Always force reset UI state
    setHasRecordingActivity(false);
    setShowPauseButton(false);

    // Always show start button after delete
    // This is important to fix the issue with state racing
    setShowStartStopButton(true);

    // Increment reset counter to trigger TranscribeButton reset
    setResetCounter((prev) => prev + 1);

    // Clear cache for this document if exists
    if (window.documentContentCache && transcriptionDocId) {
      console.log(
        `[VOICE_RECORDER] On delete: Clearing cache for document ${transcriptionDocId}`
      );
      window.documentContentCache.delete(transcriptionDocId);
    }

    // Force re-render in next tick to ensure consistent state
    requestAnimationFrame(() => {
      setShowStartStopButton(true);
    });
  };

  // Show loading state while checking audio existence
  if (isCheckingAudio) {
    return (
      <div className="flex items-center space-x-4">
        <span className="text-gray-500">Checking for existing audio...</span>
      </div>
    );
  }

  return (
    <div className="flex items-center space-x-4">
      {/* Transcribe button - modified to use our custom handler */}
      <TranscribeButton
        transcriptionDocId={transcriptionDocId}
        audioBlob={audioBlob}
        isRecording={isRecording}
        audioExists={audioExists}
        hasBeenTranscribed={hasBeenTranscribed} // Add this
        resetKey={resetCounter}
        onTranscriptionComplete={handleTranscriptionComplete}
      />

      <TimerDisplay duration={duration} />
      <MicrophoneIcon isRecording={isRecording} isPaused={isPaused} />

      {/* Only show pause/resume button during active recording */}
      {showPauseButton && (
        <PauseResumeButton
          isRecording={isRecording}
          isPaused={isPaused}
          onClick={pauseResumeRecording}
        />
      )}

      {/* Always ensure start button visibility */}
      {(showStartStopButton || (!hasRecordingActivity && !audioExists)) && (
        <StartStopButton isRecording={isRecording} onClick={handleStartStop} />
      )}

      {/* Show delete button when recording has started or completed or audio exists */}
      {(hasRecordingActivity || audioExists) && (
        <DeleteButton onClick={handleDelete} isDeleting={isDeleting} />
      )}

      <SettingsIcon />
    </div>
  );
};

export default VoiceRecorder;
