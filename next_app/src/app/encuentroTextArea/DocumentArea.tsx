import React, { useRef, useCallback, useEffect, useState } from "react";
import TabBar from "./TabBar/TabBar";
import TextArea from "./TextArea/TextArea";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorDisplay from "@/components/ErrorDisplay";
import { useDocuments } from "./hooks/useDocuments";
import { useDocumentGeneration } from "./hooks/useDocumentGeneration";
import DocumentGenerationModal from "./DocumentGenerationModal";

// Update the interface to include the new prop
interface DocumentAreaProps {
    encounterId: number;
    onTranscriptionDocumentFound?: (documentId: number) => void;
    registerGenerateDocumentationHandler?: (handler: () => void) => void;
}

const DocumentArea: React.FC<DocumentAreaProps> = ({
    encounterId,
    onTranscriptionDocumentFound,
    registerGenerateDocumentationHandler,
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
        documentContentCache,
        fetchDocumentContent,
        isLoadingContent,
        loadedDocumentIds,
        addDocument, // Assuming this function exists in useDocuments hook
    } = useDocuments(encounterId);

    // Handler for when a new document is created
    const handleDocumentCreated = useCallback(
        (newDocument) => {
            // Add the new document to the list
            addDocument(newDocument);

            // Select the new document
            selectDocument(newDocument.id);

            console.log(
                `📄 Nuevo documento creado y seleccionado: ${newDocument.id}`
            );
        },
        [addDocument, selectDocument]
    );

    // Update document generation hook to include encounterId and document creation handler
    const {
        isModalOpen,
        isGenerating,
        error: generationError,
        openGenerationModal,
        closeGenerationModal,
        generateDocumentation,
        plantillas,
        isLoadingPlantillas,
        plantillasError,
        selectedPlantillaId,
        setSelectedPlantillaId,
        searchQuery,
        setSearchQuery,
    } = useDocumentGeneration({
        documents,
        encounterId,
        onDocumentCreated: handleDocumentCreated,
    });

    // Reference to track the current editor's save function
    const currentEditorSaveRef = useRef<
        ((force?: boolean) => Promise<void>) | null
    >(null);

    // Track when a document actually needs a force refresh
    const needsRefreshRef = useRef<Set<number>>(new Set());

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

    // Create a handler function for generate documentation that we can pass to header
    const handleGenerateDocumentation = useCallback(() => {
        openGenerationModal();
    }, [openGenerationModal]);

    // Register the handler so it can be called from outside
    useEffect(() => {
        if (registerGenerateDocumentationHandler) {
            registerGenerateDocumentationHandler(handleGenerateDocumentation);
        }
    }, [registerGenerateDocumentationHandler, handleGenerateDocumentation]);

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
                onSelectDocument={handleSelectDocument}
                onGenerateDocumentation={handleGenerateDocumentation}
            />

            <div className="flex-1 overflow-auto bg-white">
                {/* Single persistent TextArea component - key set to encounterId so it only remounts 
                    when the encounter changes, not when documents change */}
                {documents.length > 0 ? (
                    <TextArea
                        key={`encounter-${encounterId}`}
                        document={activeDocument}
                        allDocuments={documents}
                        activeDocumentId={activeDocumentId}
                        readOnly={activeDocument?.tipo === "transcripcion"}
                        onSave={async (docId, content) => {
                            await saveDocument(docId, content);
                        }}
                        registerSaveFunction={registerSaveFunction}
                        documentContentCache={documentContentCache}
                        fetchDocumentContent={fetchDocumentContent}
                        isLoadingContent={isLoadingContent}
                        loadedDocumentIds={loadedDocumentIds}
                        onDocumentSwitch={(oldDocId, newDocId) => {
                            console.log(
                                `[DOC_SWITCH] Changed from document ${oldDocId} to ${newDocId}`
                            );
                            // Optional: Add any specific logic needed on document switch
                        }}
                    />
                ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                        No hay documentos disponibles para este encuentro
                    </div>
                )}
            </div>

            {/* Saving indicator */}
            {isSaving && (
                <div className="bg-blue-50 text-blue-600 text-xs p-1 border-t text-center">
                    Guardando cambios...
                </div>
            )}

            {/* Document Generation Modal */}
            <DocumentGenerationModal
                isOpen={isModalOpen}
                onClose={closeGenerationModal}
                onGenerate={generateDocumentation}
                isGenerating={isGenerating}
                error={generationError}
                plantillas={plantillas}
                isLoadingPlantillas={isLoadingPlantillas}
                plantillasError={plantillasError}
                selectedPlantillaId={selectedPlantillaId}
                setSelectedPlantillaId={setSelectedPlantillaId}
                searchQuery={searchQuery}
                setSearchQuery={setSearchQuery}
            />
        </div>
    );
};

export default DocumentArea;
