import React from "react";
import Image from "next/image";
import { MicrophoneIconProps } from "../utils/EncuentroHeaderInterface";

/**
 * Displays microphone status icon
 */
const MicrophoneIcon: React.FC<MicrophoneIconProps> = ({
    isRecording,
    isPaused,
}) => {
    let iconSrc = "/microphone_off.svg";
    let iconClass = "text-gray-500";

    if (isRecording) {
        iconSrc = isPaused ? "/microphone_paused.svg" : "/microphone_on.svg";
        iconClass = isPaused ? "text-yellow-500" : "text-red-500";
    }

    return (
        <Image
            src={iconSrc}
            alt="Microphone status"
            width={24}
            height={24}
            className={iconClass}
        />
    );
};

export default MicrophoneIcon;
