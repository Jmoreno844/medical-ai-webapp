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
    audioExists,
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

  /**
   * Update UI based on recording state
   */
  useEffect(() => {
    // Show pause button only during active recording
    setShowPauseButton(isRecording && !isPaused);

    // Show start/stop button if recording OR if not recording and no audio exists yet
    setShowStartStopButton(isRecording || !audioExists);
  }, [isRecording, isPaused, audioExists, isCheckingAudio]);

  /**
   * Handle recording start/stop
   */
  const handleStartStop = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  /**
   * Custom delete handler
   */
  const handleDelete = () => {
    deleteRecording();
  };

  // Show loading state while checking audio existence
  if (isCheckingAudio) {
    return (
      <div className="flex items-center space-x-4 p-2">
        {" "}
        {/* Added padding */}
        <div className="animate-spin rounded-full h-5 w-5 border-t-2 border-b-2 border-gray-500"></div>
        <span className="text-gray-500">Comprobando audio…</span>
      </div>
    );
  }

  return (
    <div className="flex items-center space-x-4">
      <TranscribeButton />
      <TimerDisplay duration={duration} />
      <MicrophoneIcon isRecording={isRecording} isPaused={isPaused} />

      {showPauseButton && (
        <PauseResumeButton
          isRecording={isRecording}
          isPaused={isPaused}
          onClick={pauseResumeRecording}
        />
      )}

      {showStartStopButton && (
        <StartStopButton isRecording={isRecording} onClick={handleStartStop} />
      )}

      {audioExists && !isCheckingAudio && (
        <DeleteButton onClick={handleDelete} isDeleting={isDeleting} />
      )}

      <SettingsIcon />
    </div>
  );
};

export default VoiceRecorder;
