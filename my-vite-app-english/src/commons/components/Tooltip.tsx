import React, { useState } from "react";

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactElement;
  position?: "top" | "right" | "bottom" | "left";
  delay?: number;
}

const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  position = "top",
  delay = 200,
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const [timeoutId, setTimeoutId] = useState<number | null>(null);

  const handleMouseEnter = () => {
    const id = window.setTimeout(() => setIsVisible(true), delay);
    setTimeoutId(id);
  };

  const handleMouseLeave = () => {
    if (timeoutId !== null) window.clearTimeout(timeoutId);
    setIsVisible(false);
  };

  // Position classes for tooltip
  const positionClasses = {
    top: "bottom-full mb-2 left-1/2 transform -translate-x-1/2",
    right: "left-full ml-2 top-1/2 transform -translate-y-1/2",
    bottom: "top-full mt-2 left-1/2 transform -translate-x-1/2",
    left: "right-full mr-2 top-1/2 transform -translate-y-1/2",
  };

  // Arrow classes for tooltip
  const arrowClasses = {
    top: "top-full left-1/2 transform -translate-x-1/2 border-t-gray-700 border-l-transparent border-r-transparent",
    right:
      "right-full top-1/2 transform -translate-y-1/2 border-r-gray-700 border-t-transparent border-b-transparent",
    bottom:
      "bottom-full left-1/2 transform -translate-x-1/2 border-b-gray-700 border-l-transparent border-r-transparent",
    left: "left-full top-1/2 transform -translate-y-1/2 border-l-gray-700 border-t-transparent border-b-transparent",
  };

  return (
    <div
      className="relative inline-block"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {React.cloneElement(children)}

      {isVisible && (
        <div
          className={`absolute z-50 whitespace-nowrap ${positionClasses[position]}`}
        >
          <div className="bg-gray-700 text-white text-xs py-1 px-2 rounded shadow-lg">
            {content}
          </div>
          <div
            className={`absolute w-0 h-0 border-4 ${arrowClasses[position]}`}
          ></div>
        </div>
      )}
    </div>
  );
};

export default Tooltip;
