import React from "react";

interface ErrorDisplayProps {
  message: string;
  details?: string | null;
  onRetry?: () => void;
}

const ErrorDisplay: React.FC<ErrorDisplayProps> = ({
  message,
  details,
  onRetry,
}) => {
  return (
    <div className="flex flex-col items-center justify-center h-[calc(100vh-64px)] p-4">
      <div className="bg-red-50 border border-red-200 rounded-lg max-w-md w-full p-4">
        <div className="flex items-center mb-3">
          <svg
            className="w-6 h-6 text-red-600 mr-2"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            ></path>
          </svg>
          <h3 className="text-lg font-medium text-red-600">Error</h3>
        </div>
        <p className="mb-2 text-gray-800">{message}</p>
        {details && <p className="text-sm text-gray-600">{details}</p>}
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition"
          >
            Reintentar
          </button>
        )}
      </div>
    </div>
  );
};

export default ErrorDisplay;
