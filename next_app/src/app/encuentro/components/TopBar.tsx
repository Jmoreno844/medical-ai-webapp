import React from "react";
import Image from "next/image";
import {
  TimerDisplayProps,
  MicrophoneIconProps,
  StartStopButtonProps,
  DeleteButtonProps,
} from "../utils/TopBarInterface";
import { useVoiceRecorder, formatTime } from "../utils/useTopBar";

// Component implementations
const PatientManagement: React.FC = () => (
  <div className="flex items-center space-x-2">
    <span className="text-black font-medium">Patient Management</span>
    <span className="text-black">▼</span>
  </div>
);

const TimerDisplay: React.FC<TimerDisplayProps> = ({ duration }) => (
  <div className="flex items-center space-x-2">
    <Image
      src="/clock.svg"
      alt="Timer"
      width={24}
      height={24}
      className="text-gray-500"
    />
    <span className="text-black font-mono">{formatTime(duration)}</span>
  </div>
);

const MicrophoneIcon: React.FC<MicrophoneIconProps> = ({ isRecording }) => (
  <Image
    src={isRecording ? "/microphone_on.svg" : "/microphone_off.svg"}
    alt="Microphone status"
    width={24}
    height={24}
    className={isRecording ? "text-red-500" : "text-gray-500"}
  />
);

const StartStopButton: React.FC<StartStopButtonProps> = ({
  isRecording,
  onClick,
}) => (
  <button
    onClick={onClick}
    className={`px-4 py-2 rounded-md text-white font-medium transition-colors ${
      isRecording
        ? "bg-red-500 hover:bg-red-600"
        : "bg-purple-500 hover:bg-purple-600"
    }`}
  >
    {isRecording ? "Stop" : "Start"} Recording
  </button>
);

const DeleteButton: React.FC<DeleteButtonProps> = ({ onClick }) => (
  <button
    onClick={onClick}
    className="px-4 py-2 rounded-md bg-gray-200 text-black font-medium hover:bg-gray-300 transition-colors"
  >
    Delete
  </button>
);

const SettingsIcon: React.FC = () => (
  <Image
    src="/settings.svg"
    alt="Settings"
    width={24}
    height={24}
    className="text-gray-500 hover:text-gray-700 cursor-pointer"
  />
);

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

const TopBar: React.FC = () => (
  <nav className="sticky top-0 w-full bg-white border-t border-b border-blue-200 shadow-sm z-10">
    <div className="flex justify-between items-center px-6 py-3">
      <PatientManagement />
      <VoiceRecorder />
    </div>
  </nav>
);

export default TopBar;
