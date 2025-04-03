import React from "react";

interface DocumentGenerationProgressProps {
    isGenerating: boolean;
    content: string;
    isComplete: boolean;
    error: string | null;
    onViewDocument?: () => void; // Add this prop
}

export const DocumentGenerationProgress: React.FC<
    DocumentGenerationProgressProps
> = ({ isGenerating, content, isComplete, error, onViewDocument }) => {
    if (!isGenerating && !content && !error) return null;

    return (
        <div className="mt-4 p-4 border rounded-md">
            <div className="flex justify-between items-center mb-2">
                <h3 className="text-lg font-semibold">
                    {isComplete
                        ? "Generación completada"
                        : error
                        ? "Error en la generación"
                        : "Generando documento..."}
                </h3>

                {/* Add button to view the document */}
                {onViewDocument && (
                    <button
                        onClick={onViewDocument}
                        className="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm"
                    >
                        Ver en editor
                    </button>
                )}
            </div>

            {error && (
                <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
                    <p>{error}</p>
                </div>
            )}

            {isGenerating && !error && (
                <div className="flex items-center mb-4">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500 mr-2"></div>
                    <span>Procesando...</span>
                </div>
            )}

            {content && (
                <div className="bg-white border rounded-md p-3 max-h-96 overflow-y-auto">
                    <pre className="whitespace-pre-wrap font-sans text-sm">
                        {content}
                    </pre>
                </div>
            )}
        </div>
    );
};
