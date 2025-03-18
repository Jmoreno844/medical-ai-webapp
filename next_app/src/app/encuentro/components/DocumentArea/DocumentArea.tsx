import React, { useRef, useCallback, useEffect, useState } from "react";
import TabBar from "./TabBar/TabBar";
import TextArea from "./TextArea/TextArea";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorDisplay from "@/components/ErrorDisplay";
import { useDocuments } from "../../hooks/useDocuments";

interface DocumentAreaProps {
    encounterId: number;
    onTranscriptionDocumentFound?: (documentId: number) => void;
}

const DocumentArea: React.FC<DocumentAreaProps> = ({
    encounterId,
    onTranscriptionDocumentFound,
}) => {
    const {
        documents,
        activeDocument,
        activeDocumentId,
        loading,
        error,
        isSaving,
        selectDocument,
        saveDocument,
        // Extract these additional props from useDocuments
        documentContentCache,
        fetchDocumentContent,
        isLoadingContent,
        loadedDocumentIds,
    } = useDocuments(encounterId);

    // Reference to track the current editor's save function
    const currentEditorSaveRef = useRef<
        ((force?: boolean) => Promise<void>) | null
    >(null);

    // Keep track of documents we've already loaded to ensure proper key changes
    const [documentVersions, setDocumentVersions] = useState<
        Record<number, number>
    >({});

    // Find and emit transcription document ID when documents load
    useEffect(() => {
        if (!loading && documents.length > 0 && onTranscriptionDocumentFound) {
            const transcriptionDoc = documents.find(
                (doc) => doc.tipo === "transcripcion"
            );
            if (transcriptionDoc) {
                onTranscriptionDocumentFound(transcriptionDoc.id);
            }
        }
    }, [documents, loading, onTranscriptionDocumentFound]);

    // Register a save function provided by the TextArea component
    const registerSaveFunction = useCallback(
        (saveFunc: (force?: boolean) => Promise<void>) => {
            currentEditorSaveRef.current = saveFunc;
        },
        []
    );

    // Update document version when switching documents
    useEffect(() => {
        if (activeDocumentId) {
            setDocumentVersions((prev) => ({
                ...prev,
                [activeDocumentId]: (prev[activeDocumentId] || 0) + 1,
            }));
        }
    }, [activeDocumentId]);

    // Handle document selection with saving
    const handleSelectDocument = useCallback(
        async (docId: number) => {
            if (activeDocumentId !== docId) {
                // Trigger save on the current document before switching
                if (currentEditorSaveRef.current) {
                    try {
                        console.log(
                            `[DOC_TAB] Saving document ${activeDocumentId} before switching to ${docId}`
                        );
                        await currentEditorSaveRef.current(true); // Force save
                    } catch (err) {
                        console.error(
                            `[DOC_TAB ❌] Failed to save document ${activeDocumentId} during tab change:`,
                            err
                        );
                    }
                }

                console.log(
                    `[DOC_TAB] Switching from document ${activeDocumentId} to ${docId}`
                );
                // Then switch to the new document
                selectDocument(docId);
            }
        },
        [activeDocumentId, selectDocument]
    );

    if (loading) {
        return (
            <div className="flex flex-col h-full">
                <div className="bg-gray-100 p-2 border-b text-sm text-gray-500">
                    Cargando documentos...
                </div>
                <div className="flex-1 flex items-center justify-center">
                    <LoadingSpinner />
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col h-full">
                <div className="bg-gray-100 p-2 border-b text-sm text-gray-500">
                    Error al cargar documentos
                </div>
                <div className="flex-1">
                    <ErrorDisplay
                        message="No se pudieron cargar los documentos"
                        details={error}
                    />
                </div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full border rounded-md overflow-hidden">
            <TabBar
                documents={documents}
                activeDocumentId={activeDocumentId}
                onSelectDocument={handleSelectDocument} // Use our wrapped handler
            />

            <div className="flex-1 overflow-auto bg-white">
                {activeDocument ? (
                    <TextArea
                        // Use document version in key to ensure proper remounting
                        key={`doc-${activeDocument.id}-v${
                            documentVersions[activeDocument.id] || 1
                        }`}
                        document={activeDocument}
                        readOnly={false}
                        onSave={async (docId, content) => {
                            await saveDocument(docId, content); // Discard the boolean result
                            // Returns void implicitly
                        }}
                        registerSaveFunction={registerSaveFunction}
                        // Pass these additional props to TextArea
                        documentContentCache={documentContentCache}
                        fetchDocumentContent={fetchDocumentContent}
                        isLoadingContent={isLoadingContent}
                        isDocumentLoaded={loadedDocumentIds.includes(
                            activeDocument.id
                        )}
                    />
                ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                        {documents.length > 0
                            ? "Seleccione un documento para visualizar"
                            : "No hay documentos disponibles para este encuentro"}
                    </div>
                )}
            </div>

            {/* Saving indicator */}
            {isSaving && (
                <div className="bg-blue-50 text-blue-600 text-xs p-1 border-t text-center">
                    Guardando cambios...
                </div>
            )}
        </div>
    );
};

export default DocumentArea;
