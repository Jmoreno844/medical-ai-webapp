import React from "react";
import Image from "next/image";

/**
 * Settings icon button
 */
const SettingsIcon: React.FC = () => (
  <Image
    src="/settings.svg"
    alt="Settings"
    width={24}
    height={24}
    className="text-gray-500 hover:text-gray-700 cursor-pointer"
  />
);

export default SettingsIcon;
