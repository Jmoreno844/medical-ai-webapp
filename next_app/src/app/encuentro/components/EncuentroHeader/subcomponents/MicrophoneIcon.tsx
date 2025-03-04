import React from "react";
import Image from "next/image";
import { MicrophoneIconProps } from "../../../utils/EncuentroHeaderInterface";

/**
 * Displays microphone status icon
 */
const MicrophoneIcon: React.FC<MicrophoneIconProps> = ({ isRecording }) => (
  <Image
    src={isRecording ? "/microphone_on.svg" : "/microphone_off.svg"}
    alt="Microphone status"
    width={24}
    height={24}
    className={isRecording ? "text-red-500" : "text-gray-500"}
  />
);

export default MicrophoneIcon;
