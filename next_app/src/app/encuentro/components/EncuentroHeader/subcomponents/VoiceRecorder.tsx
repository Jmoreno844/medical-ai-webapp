import React, { useEffect, useState } from "react";
import { useVoiceRecorder } from "../../../hooks/useVoiceRecorder";
import TimerDisplay from "./TimerDisplay";
import MicrophoneIcon from "./MicrophoneIcon";
import StartStopButton from "./StartStopButton";
import PauseResumeButton from "./PauseResumeButton";
import DeleteButton from "./DeleteButton";
import SettingsIcon from "./SettingsIcon";
import TranscribeButton from "./TranscribeButton";

/**
 * Props for the VoiceRecorder component
 */
interface VoiceRecorderProps {
  /** ID of the transcription document if available */
  transcriptionDocId?: number;
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
}) => {
  // Use our cleaned up voice recorder hook
  const {
    isRecording,
    isPaused,
    duration,
    audioBlob,
    startRecording,
    stopRecording,
    pauseResumeRecording,
    deleteRecording,
  } = useVoiceRecorder(transcriptionDocId);

  // UI state management
  const [showPauseButton, setShowPauseButton] = useState(false);
  const [showStartStopButton, setShowStartStopButton] = useState(true);
  const [hasRecordingActivity, setHasRecordingActivity] = useState(false);

  /**
   * Update UI based on recording state
   */
  useEffect(() => {
    // Only show pause button during active recording, hide when stopped
    setShowPauseButton(isRecording);

    // Hide start/stop button only when we have a completed recording
    if (!isRecording && audioBlob) {
      setShowStartStopButton(false);
    } else {
      setShowStartStopButton(true);
    }
  }, [isRecording, audioBlob]);

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
    const wasRecording = isRecording;

    // Call the hook's delete function
    deleteRecording();

    // Always force reset UI state
    setHasRecordingActivity(false);
    setShowPauseButton(false);

    // Always show start button after delete
    // This is important to fix the issue with state racing
    setShowStartStopButton(true);

    // Force re-render in next tick to ensure consistent state
    requestAnimationFrame(() => {
      setShowStartStopButton(true);
    });
  };

  return (
    <div className="flex items-center space-x-4">
      {/* Transcribe button - new addition */}
      <TranscribeButton
        transcriptionDocId={transcriptionDocId}
        audioBlob={audioBlob}
        isRecording={isRecording}
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
      {(showStartStopButton || !hasRecordingActivity) && (
        <StartStopButton isRecording={isRecording} onClick={handleStartStop} />
      )}

      {/* Show delete button when recording has started or completed */}
      {hasRecordingActivity && <DeleteButton onClick={handleDelete} />}

      <SettingsIcon />
    </div>
  );
};

export default VoiceRecorder;
