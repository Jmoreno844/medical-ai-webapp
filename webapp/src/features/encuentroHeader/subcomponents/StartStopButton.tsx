import React from "react";
import { StartStopButtonProps } from "../utils/EncuentroHeaderInterface";

/**
 * Button to start or stop recording
 */
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
        {isRecording ? "Detener" : "Iniciar"} grabación
    </button>
);

export default StartStopButton;
