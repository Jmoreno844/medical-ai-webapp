import React, { useRef, useCallback, useEffect, useState } from "react";
import TabBar from "./TabBar/TabBar";
import TextArea from "./TextArea/TextArea";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorDisplay from "@/components/ErrorDisplay";
import { useDocuments } from "./hooks/useDocuments";
import { useDocumentGeneration } from "./hooks/useDocumentGeneration";
import DocumentGenerationModal from "./DocumentGenerationModal";
import { DocumentGenerationProgress } from "./components/DocumentGenerationProgress";

// Update the interface to include the new prop
interface DocumentAreaProps {
    encounterId: number;
    onTranscriptionDocumentFound?: (documentId: number) => void;
    registerGenerateDocumentationHandler?: (handler: () => void) => void;
    transcriptionCompleteTimestamp?: number | null;
    transcriptionDocId?: number;
}

const DocumentArea: React.FC<DocumentAreaProps> = ({
    encounterId,
    onTranscriptionDocumentFound,
    registerGenerateDocumentationHandler,
    transcriptionCompleteTimestamp,
    transcriptionDocId,
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
        deleteDocument, // Add deleteDocument from the hook
    } = useDocuments(encounterId);

    // Add state to track content updates and trigger refreshes
    const [refreshTrigger, setRefreshTrigger] = useState(0);

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

    // Document content update handler for SSE generation
    const handleContentUpdate = useCallback(
        async (documentId: number, content: string) => {
            console.log(
                `[DOC_UPDATE] Saving streamed content to document ${documentId} (${content.length} chars)`
            );

            try {
                // Save the content to the document
                await saveDocument(documentId, content);

                // Find the document to determine its type
                const updatedDoc = documents.find(
                    (doc) => doc.id === documentId
                );
                const isTranscription = updatedDoc?.tipo === "transcripcion";

                // If this is the active document AND it's a transcription, trigger a refresh
                if (activeDocumentId === documentId && isTranscription) {
                    console.log(
                        "[DOC_UPDATE] Active transcription document updated, triggering refresh"
                    );
                    setRefreshTrigger((prev) => prev + 1);
                }
            } catch (err) {
                console.error(
                    "[DOC_UPDATE] Error saving streamed content:",
                    err
                );
            }
        },
        [saveDocument, activeDocumentId, documents]
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
        generationStatus,
    } = useDocumentGeneration({
        documents,
        encounterId,
        onDocumentCreated: handleDocumentCreated,
        onContentUpdate: handleContentUpdate,
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
    // This should only open the modal, not generate the document yet
    const handleGenerateDocumentation = useCallback(() => {
        openGenerationModal();
    }, [openGenerationModal]);

    // New function to handle generation after plantilla selection
    const handleExecuteGeneration = useCallback(async () => {
        try {
            const newDocument = await generateDocumentation();

            // If generation was successful and returned a document,
            // select it immediately to show it in the editor
            if (newDocument && newDocument.id) {
                handleSelectDocument(newDocument.id);
            }
            return newDocument;
        } catch (error) {
            console.error("Error generating documentation:", error);
            return null;
        }
    }, [generateDocumentation, handleSelectDocument]);

    // Register the handler so it can be called from outside
    useEffect(() => {
        if (registerGenerateDocumentationHandler) {
            registerGenerateDocumentationHandler(handleGenerateDocumentation);
        }
    }, [registerGenerateDocumentationHandler, handleGenerateDocumentation]);

    // Add these refs to track polling state and document content
    const processedTimestampsRef = useRef(new Set<number>());
    const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);
    const contentLengthRef = useRef<number>(0);
    const lastAttemptTimeRef = useRef<number>(0);

    // React to transcription complete events with smarter polling
    useEffect(() => {
        console.log("[DOC_AREA] Effect triggered with", {
            transcriptionCompleteTimestamp,
            transcriptionDocId,
            activeDocumentId,
            cacheExists: documentContentCache
                ? documentContentCache.has(transcriptionDocId as number)
                : false,
        });

        // Skip if we've already processed this timestamp
        if (
            transcriptionCompleteTimestamp &&
            processedTimestampsRef.current.has(transcriptionCompleteTimestamp)
        ) {
            console.log(
                `[DOC_AREA] Already processed timestamp ${transcriptionCompleteTimestamp}, skipping`
            );
            return;
        }

        // Clear any existing polling timer
        if (pollingTimerRef.current) {
            clearTimeout(pollingTimerRef.current);
            pollingTimerRef.current = null;
        }

        if (
            transcriptionCompleteTimestamp &&
            transcriptionDocId &&
            activeDocumentId === transcriptionDocId
        ) {
            console.log(
                "[DOC_AREA] Detected transcription complete while viewing transcription document"
            );

            // Mark this timestamp as processed
            if (transcriptionCompleteTimestamp) {
                processedTimestampsRef.current.add(
                    transcriptionCompleteTimestamp
                );
            }

            // Check if document already has content of significant length
            const checkContentLength = async () => {
                if (documentContentCache && transcriptionDocId) {
                    const cachedContent =
                        documentContentCache.get(transcriptionDocId);
                    if (cachedContent && cachedContent.length > 20) {
                        console.log(
                            `[DOC_AREA] Document ${transcriptionDocId} already has content of length ${cachedContent.length}, no polling needed`
                        );
                        return true;
                    }
                }

                // If fetchDocumentContent exists, try getting current content length
                if (fetchDocumentContent && transcriptionDocId) {
                    try {
                        const content = await fetchDocumentContent(
                            transcriptionDocId
                        );
                        if (content && content.length > 20) {
                            console.log(
                                `[DOC_AREA] Fresh content already available with length ${content.length}, no polling needed`
                            );
                            return true;
                        }
                    } catch (err) {
                        console.log(
                            "[DOC_AREA] Error checking current content:",
                            err
                        );
                    }
                }

                return false;
            };

            // Function to poll for content with early termination
            const attemptContentRefresh = async (
                attempt: number = 1,
                maxAttempts: number = 8
            ) => {
                // Stop if more than 100ms hasn't passed since last attempt (prevents double triggers)
                const now = Date.now();
                if (now - lastAttemptTimeRef.current < 100 && attempt > 1) {
                    console.log(
                        `[DOC_AREA] Skipping attempt ${attempt} - too close to previous attempt`
                    );
                    return;
                }
                lastAttemptTimeRef.current = now;

                console.log(
                    `[DOC_AREA] Polling attempt ${attempt}/${maxAttempts} for document ${transcriptionDocId}`
                );

                // First check if content already exists
                const hasContent = await checkContentLength();
                if (hasContent) {
                    console.log(
                        `[DOC_AREA] Content already available, stopping polling`
                    );
                    return;
                }

                // Clear document from cache to force a fresh load
                if (documentContentCache && transcriptionDocId) {
                    console.log(
                        `[DOC_AREA] Clearing cached content for document ${transcriptionDocId}`
                    );
                    documentContentCache.delete(transcriptionDocId);
                }

                // Trigger the content refresh
                setRefreshTrigger((prev) => {
                    const newTrigger = prev + 1;
                    console.log(
                        `[DOC_AREA] Refresh trigger updated to ${newTrigger} (attempt ${attempt})`
                    );
                    return newTrigger;
                });

                // Wait a bit to let the content load before checking
                await new Promise((resolve) => setTimeout(resolve, 250));

                // Check if content was loaded after refresh
                const contentLoaded = await checkContentLength();
                if (contentLoaded) {
                    console.log(
                        `[DOC_AREA] Content loaded successfully after attempt ${attempt}, stopping polling`
                    );
                    return;
                }

                // If we haven't reached max attempts and no content yet, schedule another try
                if (attempt < maxAttempts) {
                    // Calculate next delay with exponential backoff (500ms, 1000ms, etc.)
                    const nextDelay = Math.min(
                        500 * Math.pow(1.5, attempt - 1),
                        1000
                    );

                    console.log(
                        `[DOC_AREA] Content not loaded yet. Scheduling next polling attempt in ${nextDelay}ms`
                    );
                    pollingTimerRef.current = setTimeout(() => {
                        attemptContentRefresh(attempt + 1, maxAttempts);
                    }, nextDelay);
                } else {
                    console.log(
                        `[DOC_AREA] Reached maximum polling attempts (${maxAttempts})`
                    );
                }
            };

            // Start polling immediately (but asynchronously)
            setTimeout(() => {
                attemptContentRefresh();
            }, 0);
        }

        // Cleanup function to clear any polling timers when component unmounts or dependencies change
        return () => {
            if (pollingTimerRef.current) {
                clearTimeout(pollingTimerRef.current);
                pollingTimerRef.current = null;
            }
        };
    }, [
        transcriptionCompleteTimestamp,
        activeDocumentId,
        transcriptionDocId,
        fetchDocumentContent,
    ]);

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
                onDeleteDocument={deleteDocument} // Pass the delete function
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
                        }}
                        refreshTrigger={refreshTrigger}
                        generationStatus={generationStatus} // Pass generation status to TextArea
                    />
                ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                        No hay documentos disponibles para este encuentro
                    </div>
                )}
            </div>

            {/* Display real-time generation progress when active outside the modal
                Only show when we're not already viewing the document being generated */}
            {!isModalOpen &&
                generationStatus?.inProgress &&
                activeDocumentId !== generationStatus.documentId && (
                    <div className="p-4 bg-white border-t">
                        <DocumentGenerationProgress
                            isGenerating={generationStatus.inProgress}
                            content={generationStatus.content}
                            isComplete={generationStatus.isComplete}
                            error={generationStatus.error}
                            onViewDocument={
                                generationStatus.documentId
                                    ? () =>
                                          handleSelectDocument(
                                              generationStatus.documentId!
                                          )
                                    : undefined
                            }
                        />
                    </div>
                )}

            {/* Saving indicator */}
            {isSaving && (
                <div className="bg-blue-50 text-blue-600 text-xs p-1 border-t text-center">
                    Guardando cambios...
                </div>
            )}

            {/* Document Generation Modal - now with updated props */}
            <DocumentGenerationModal
                isOpen={isModalOpen}
                onClose={closeGenerationModal}
                onGenerate={handleExecuteGeneration} // Use the execution handler here
                isGenerating={isGenerating}
                error={generationError}
                plantillas={plantillas}
                isLoadingPlantillas={isLoadingPlantillas}
                plantillasError={plantillasError}
                selectedPlantillaId={selectedPlantillaId}
                setSelectedPlantillaId={setSelectedPlantillaId}
                searchQuery={searchQuery}
                setSearchQuery={setSearchQuery}
                generationStatus={generationStatus}
            />
        </div>
    );
};

export default DocumentArea;
