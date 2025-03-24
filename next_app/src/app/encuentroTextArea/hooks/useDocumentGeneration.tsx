import { useState, useCallback, useEffect } from "react";
import { DocumentoOut } from "@/types/documento";
import axiosInstance from "@/utils/axiosInstance";

interface Plantilla {
    id: number;
    nombre: string;
    tipo_documento: string;
    fecha_creacion: string;
    es_base: boolean;
    veces_usada: number;
    ultimo_uso: string | null;
}

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

    // Template related state
    const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
    const [isLoadingPlantillas, setIsLoadingPlantillas] = useState(false);
    const [plantillasError, setPlantillasError] = useState<string | null>(null);
    const [selectedPlantillaId, setSelectedPlantillaId] = useState<
        number | null
    >(null);
    const [searchQuery, setSearchQuery] = useState("");

    // Fetch plantillas when modal opens
    useEffect(() => {
        if (isModalOpen) {
            fetchPlantillas();
        }
    }, [isModalOpen]);

    const fetchPlantillas = useCallback(async () => {
        try {
            setIsLoadingPlantillas(true);
            setPlantillasError(null);

            const response = await axiosInstance.get("/api/plantillas_short");
            setPlantillas(response.data || []);

            // Select first template by default if available
            if (response.data && response.data.length > 0) {
                setSelectedPlantillaId(response.data[0].id);
            }
        } catch (err) {
            console.error("❌ Error al cargar plantillas:", err);
            setPlantillasError("No se pudieron cargar las plantillas");
        } finally {
            setIsLoadingPlantillas(false);
        }
    }, []);

    const openGenerationModal = useCallback(() => {
        setIsModalOpen(true);
        setError(null);
    }, []);

    const closeGenerationModal = useCallback(() => {
        setIsModalOpen(false);
        setSearchQuery("");
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
            if (!selectedPlantillaId) {
                throw new Error("Por favor seleccione una plantilla");
            }

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
                idPlantilla: selectedPlantillaId,
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
    }, [documents, createNewDocument, selectedPlantillaId]);

    // Filter plantillas based on search query
    const filteredPlantillas = searchQuery
        ? plantillas.filter((p) =>
              p.nombre.toLowerCase().includes(searchQuery.toLowerCase())
          )
        : plantillas;

    return {
        isModalOpen,
        isGenerating,
        error,
        openGenerationModal,
        closeGenerationModal,
        generateDocumentation,
        plantillas: filteredPlantillas,
        isLoadingPlantillas,
        plantillasError,
        selectedPlantillaId,
        setSelectedPlantillaId,
        searchQuery,
        setSearchQuery,
    };
}
