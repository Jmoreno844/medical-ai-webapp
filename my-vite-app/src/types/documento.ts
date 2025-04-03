export interface DocumentoOut {
    id: number;
    id_encuentro: number;
    tipo: string;
    id_plantilla_doctor?: number;
    contenido: string;
    fecha_creacion: string; // ISO date string
    id_medico: number;
}

// Document type labels for tab display
export const DOCUMENT_TYPE_LABELS: Record<string, string> = {
    nota: "Nota Clínica",
    receta: "Receta Médica",
    laboratorio: "Órden Laboratorio",
    imagen: "Órden Imagen",
    certificado: "Certificado",
    contexto: "Contexto",
    transcripcion: "Transcripción",
};

// Longer document type labels for full display
export const DOCUMENT_TYPE_LABELS_LONG: Record<string, string> = {
    nota: "Nota Clínica",
    receta: "Receta Médica",
    laboratorio: "Órden de Laboratorio",
    imagen: "Órden de Imagen",
    certificado: "Certificado Médico",
    contexto: "Contexto",
    transcripcion: "Transcripción",
};
