import React from "react";
import { PauseResumeButtonProps } from "../../../utils/EncuentroHeaderInterface";

/**
 * Button to pause or resume recording
 */
const PauseResumeButton: React.FC<PauseResumeButtonProps> = ({
  isRecording,
  isPaused,
  onClick,
}) => (
  <button
    onClick={onClick}
    disabled={!isRecording}
    className={`px-4 py-2 rounded-md text-white font-medium transition-colors ${
      !isRecording
        ? "bg-gray-300 cursor-not-allowed"
        : isPaused
        ? "bg-yellow-500 hover:bg-yellow-600"
        : "bg-blue-500 hover:bg-blue-600"
    }`}
  >
    {isPaused ? "Resume" : "Pause"}
  </button>
);

export default PauseResumeButton;
