import React from "react";
import Image from "next/image";
import { TimerDisplayProps } from "../utils/EncuentroHeaderInterface";
import { formatTime } from "../hooks/audio/utils";

/**
 * Displays the recording timer
 */
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

export default TimerDisplay;
