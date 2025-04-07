import React, { useState, useEffect } from "react";
import TimerDisplay from "./TimerDisplay";
import MicrophoneIcon from "./MicrophoneIcon";
import StartStopButton from "./StartStopButton";
import PauseResumeButton from "./PauseResumeButton";
import DeleteButton from "./DeleteButton";
import SettingsIcon from "./SettingsIcon";
import TranscribeButton from "./TranscribeButton";
import { useTranscriptionContext } from "../../../contexts/TranscriptionContext";

/**
 * Voice recorder component with controls
 *
 * Provides UI for recording, pausing, stopping and deleting voice recordings
 * Now uses TranscriptionContext for all state and actions
 *
 * @returns React component
 */
const VoiceRecorder: React.FC = () => {
  // Use transcription context
  const {
    isRecording,
    isPaused,
    duration,
    audioBlob,
    audioExists,
    isCheckingAudio,
    isDeleting,
    startRecording,
    stopRecording,
    pauseResumeRecording,
    deleteRecording,
  } = useTranscriptionContext();

  // UI state management
  const [showPauseButton, setShowPauseButton] = useState(false);
  const [showStartStopButton, setShowStartStopButton] = useState(true);
  const [hasRecordingActivity, setHasRecordingActivity] = useState(false);
  const [resetCounter, setResetCounter] = useState(0);

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
    // Call the context's delete function
    deleteRecording();

    // Reset UI state
    setHasRecordingActivity(false);
    setShowPauseButton(false);
    setShowStartStopButton(true);

    // Increment reset counter to trigger TranscribeButton reset
    setResetCounter((prev) => prev + 1);

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
      {/* Transcribe button now uses context directly through its own component */}
      <TranscribeButton resetKey={resetCounter} />

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
