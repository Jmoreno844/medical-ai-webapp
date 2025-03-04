import React from "react";
import { useVoiceRecorder } from "../../../hooks/useEncuentroHeader";
import TimerDisplay from "./TimerDisplay";
import MicrophoneIcon from "./MicrophoneIcon";
import StartStopButton from "./StartStopButton";
import DeleteButton from "./DeleteButton";
import SettingsIcon from "./SettingsIcon";

/**
 * Voice recorder component with controls
 */
const VoiceRecorder: React.FC = () => {
  const {
    isRecording,
    duration,
    startRecording,
    stopRecording,
    deleteRecording,
  } = useVoiceRecorder();

  return (
    <div className="flex items-center space-x-4">
      <TimerDisplay duration={duration} />
      <MicrophoneIcon isRecording={isRecording} />
      <StartStopButton
        isRecording={isRecording}
        onClick={isRecording ? stopRecording : startRecording}
      />
      <DeleteButton onClick={deleteRecording} />
      <SettingsIcon />
    </div>
  );
};

export default VoiceRecorder;
