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
    // audioBlob, // No longer needed for visibility logic here
    audioExists, // Use this directly
    isCheckingAudio,
    isDeleting,
    startRecording,
    stopRecording,
    pauseResumeRecording,
    deleteRecording,
  } = useTranscriptionContext();

  // UI state management - Simplified
  const [showPauseButton, setShowPauseButton] = useState(false);
  const [showStartStopButton, setShowStartStopButton] = useState(true);
  // Remove hasRecordingActivity state
  // Remove resetCounter state

  /**
   * Update UI based on recording state
   */
  useEffect(() => {
    // Show pause button only during active recording
    setShowPauseButton(isRecording && !isPaused);

    // Show start/stop button if not recording AND audio doesn't exist yet
    // Or if checking audio (initial state)
    setShowStartStopButton(!isRecording && !audioExists);

    // Note: No need to manage hasRecordingActivity anymore
  }, [isRecording, isPaused, audioExists, isCheckingAudio]); // Updated dependencies

  /**
   * Handle recording start/stop
   */
  const handleStartStop = () => {
    if (isRecording) {
      if (isPaused) {
        pauseResumeRecording();
      }
      stopRecording();
      // No need to set hasRecordingActivity
    } else {
      startRecording();
      // No need to set hasRecordingActivity
    }
  };

  /**
   * Custom delete handler
   */
  const handleDelete = () => {
    deleteRecording();
    // Reset UI state - simplified
    setShowPauseButton(false);
    setShowStartStopButton(true); // Show start button after delete
    // No need to manage hasRecordingActivity or resetCounter
  };

  // Show loading state while checking audio existence
  if (isCheckingAudio) {
    return (
      <div className="flex items-center space-x-4 p-2">
        {" "}
        {/* Added padding */}
        <div className="animate-spin rounded-full h-5 w-5 border-t-2 border-b-2 border-gray-500"></div>
        <span className="text-gray-500">Checking audio...</span>
      </div>
    );
  }

  return (
    <div className="flex items-center space-x-4">
      {/* Transcribe button - remove resetKey */}
      <TranscribeButton />

      <TimerDisplay duration={duration} />
      <MicrophoneIcon isRecording={isRecording} isPaused={isPaused} />

      {/* Show pause/resume button only during active, unpaused recording */}
      {isRecording && (
        <PauseResumeButton
          isRecording={isRecording}
          isPaused={isPaused}
          onClick={pauseResumeRecording}
        />
      )}

      {/* Show start/stop button if not recording AND audio doesn't exist */}
      {showStartStopButton && (
        <StartStopButton isRecording={isRecording} onClick={handleStartStop} />
      )}

      {/* Show delete button ONLY if audio exists for the current encounter */}
      {/* Ensure it's not shown while checking */}
      {audioExists && !isCheckingAudio && (
        <DeleteButton onClick={handleDelete} isDeleting={isDeleting} />
      )}

      <SettingsIcon />
    </div>
  );
};

export default VoiceRecorder;
