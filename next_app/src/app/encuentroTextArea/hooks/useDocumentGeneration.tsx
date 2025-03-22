import { useState, useCallback } from "react";
import { DocumentoOut } from "@/types/documento";
import axiosInstance from "@/utils/axiosInstance";

interface UseDocumentGenerationProps {
    documents: DocumentoOut[];
    encounterId: number;
    onDocumentCreated?: (newDocument: DocumentoOut) => void;
}

export function useDocumentGeneration({
    documents,
    encounterId,
    onDocumentCreated,
}: UseDocumentGenerationProps) {
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [isGenerating, setIsGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const openGenerationModal = useCallback(() => {
        setIsModalOpen(true);
        setError(null);
    }, []);

    const closeGenerationModal = useCallback(() => {
        setIsModalOpen(false);
    }, []);

    const createNewDocument = useCallback(async () => {
        try {
            // Call API to create new empty document of type "nota"
            const response = await axiosInstance.post("/api/documento", {
                id_encuentro: encounterId,
                tipo: "nota",
            });

            console.log("📄 Documento nuevo creado:", response.data);

            // Call the callback with the new document
            if (onDocumentCreated && response.data) {
                onDocumentCreated(response.data);
            }

            return response.data;
        } catch (err) {
            console.error("❌ Error al crear nuevo documento:", err);
            throw err;
        }
    }, [encounterId, onDocumentCreated]);

    const generateDocumentation = useCallback(async () => {
        try {
            setIsGenerating(true);
            setError(null);

            // Find transcription and context documents
            const transcriptionDoc = documents.find(
                (doc) => doc.tipo === "transcripcion"
            );
            const contextDoc = documents.find((doc) => doc.tipo === "contexto");

            if (!transcriptionDoc) {
                throw new Error("No se encontró el documento de transcripción");
            }

            if (!contextDoc) {
                throw new Error("No se encontró el documento de contexto");
            }

            console.log("📄 Documentos encontrados:", {
                transcripcion: transcriptionDoc.id,
                contexto: contextDoc.id,
            });

            // Here you would make the API call with just the document IDs
            console.log("🚀 Generando documentación con IDs:", {
                idTranscripcion: transcriptionDoc.id,
                idContexto: contextDoc.id,
            });

            // Mock API call for now
            await new Promise((resolve) => setTimeout(resolve, 2000));

            // Success!
            console.log("✅ Documentación generada con éxito");

            // Create new document after successful generation
            const newDocument = await createNewDocument();

            setIsModalOpen(false);

            // Return the newly created document
            return newDocument;
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error desconocido");
            console.error("❌ Error generando documentación:", err);
            return null;
        } finally {
            setIsGenerating(false);
        }
    }, [documents, createNewDocument]);

    return {
        isModalOpen,
        isGenerating,
        error,
        openGenerationModal,
        closeGenerationModal,
        generateDocumentation,
    };
}
