import React from "react";
import { Pause, Play } from "lucide-react";
import { PauseResumeButtonProps } from "../utils/EncuentroHeaderInterface";

/**
 * Button to pause or resume recording
 */
const PauseResumeButton: React.FC<PauseResumeButtonProps> = ({
  isRecording,
  isPaused,
  onClick,
}) => {
  const label = isPaused ? "Reanudar" : "Pausar";
  return (
    <button
      onClick={onClick}
      disabled={!isRecording}
      aria-label={label}
      title={label}
      className={`inline-flex items-center justify-center rounded-md px-4 py-2 font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-1 ${
        !isRecording
          ? "cursor-not-allowed border border-gray-200 bg-gray-100 text-gray-400"
          : "border border-slate-300 bg-slate-100 text-slate-700 hover:border-slate-400 hover:bg-slate-200 hover:text-slate-900"
      }`}
    >
      {isPaused ? (
        <Play size={18} strokeWidth={2.25} fill="currentColor" />
      ) : (
        <Pause size={18} strokeWidth={2.25} />
      )}
    </button>
  );
};

export default PauseResumeButton;
