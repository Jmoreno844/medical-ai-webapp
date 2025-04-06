import React from "react";

interface GenerateDocumentationButtonProps {
  onClick: () => void;
  disabled?: boolean;
  hasBeenTranscribed: boolean;
}

const GenerateDocumentationButton: React.FC<
  GenerateDocumentationButtonProps
> = ({ onClick, disabled = false }) => {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center px-3 py-1.5 rounded text-base font-medium transition-colors
                ${
                  disabled
                    ? "bg-gray-200 text-gray-500 cursor-not-allowed"
                    : "bg-purple-500 text-white hover:bg-purple-700 rounded-md"
                }`}
      title="Generar documentación médica"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-4 w-4 mr-1"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
      Generate
    </button>
  );
};

export default GenerateDocumentationButton;
