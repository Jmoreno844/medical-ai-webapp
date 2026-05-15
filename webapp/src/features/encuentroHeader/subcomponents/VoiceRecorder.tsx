import React from "react";
import TimerDisplay from "./TimerDisplay";
import MicrophoneIcon from "./MicrophoneIcon";
import PauseResumeButton from "./PauseResumeButton";
import SettingsIcon from "./SettingsIcon";
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
    transcriptionDocId,
    isRecording,
    isPaused,
    duration,
    audioExists,
    pendingAudioSections,
    transcriptionStatus,
    audioExpiresAt,
    isAudioExpired,
    isCheckingAudio,
    startRecording,
    stopRecording,
    pauseResumeRecording,
  } = useTranscriptionContext();

  /**
   * Handle the single primary audio action.
   *
   * The primary button controls the recording session lifecycle. Stopping the
   * session finalizes the current near realtime transcription window, and the
   * idle state becomes "Reanudar" for the next session on the same encounter.
   */
  const handlePrimaryAudioAction = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const expiredMessage = audioExpiresAt
    ? `Audio expirado el ${new Date(audioExpiresAt).toLocaleString()}`
    : "Audio expirado";

  const hasTranscriptionActivity =
    isRecording ||
    pendingAudioSections > 0 ||
    transcriptionStatus === "pending";

  const statusLabel = isRecording
    ? "Transcripción automática en curso"
    : pendingAudioSections > 0
      ? "Transcripción pendiente"
      : "Consolidando transcripción…";

  const primaryAudioLabel = isRecording
    ? "Detener transcripción"
    : !transcriptionDocId
      ? "Preparando..."
    : audioExists || pendingAudioSections > 0 || isAudioExpired
      ? isAudioExpired
        ? "Grabar de nuevo"
        : "Reanudar"
      : "Grabar";

  const primaryAudioButtonClasses = `px-4 py-2 rounded-md text-white font-medium transition-colors ${
    !transcriptionDocId && !isRecording
      ? "bg-gray-300 cursor-not-allowed"
      : isRecording
      ? "bg-red-500 hover:bg-red-600"
      : "bg-purple-500 hover:bg-purple-600"
  }`;

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
      {isAudioExpired && (
        <span className="rounded-md bg-amber-100 px-2 py-1 text-sm font-medium text-amber-800">
          {expiredMessage}
        </span>
      )}

      {isRecording && (
        <PauseResumeButton
          isRecording={isRecording}
          isPaused={isPaused}
          onClick={pauseResumeRecording}
        />
      )}
      <button
        onClick={handlePrimaryAudioAction}
        className={primaryAudioButtonClasses}
        aria-label={primaryAudioLabel}
        disabled={!transcriptionDocId && !isRecording}
      >
        {primaryAudioLabel}
      </button>

      <MicrophoneIcon isRecording={isRecording} isPaused={isPaused} />
      <TimerDisplay duration={duration} />
      {hasTranscriptionActivity && (
        <div className="flex items-center gap-2 rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-sm text-violet-800">
          <div className="h-2 w-2 rounded-full bg-violet-500 animate-pulse" />
          <span className="font-medium">{statusLabel}</span>
        </div>
      )}

      <SettingsIcon />
    </div>
  );
};

export default VoiceRecorder;
