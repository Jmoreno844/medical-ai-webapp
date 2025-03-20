import React, { useMemo } from "react";
import { DocumentoOut } from "@/types/documento";

interface TabBarProps {
  documents: DocumentoOut[];
  activeDocumentId: number | null;
  onSelectDocument: (documentId: number) => void;
}

const TabBar: React.FC<TabBarProps> = ({
  documents,
  activeDocumentId,
  onSelectDocument,
}) => {
  // Sort documents with a stable sort order that won't change between renders
  const sortedDocuments = useMemo(() => {
    // Create a new array to avoid mutating the original
    return [...documents].sort((a, b) => {
      // Primary sort by creation date
      const dateA = new Date(a.fecha_creacion).getTime();
      const dateB = new Date(b.fecha_creacion).getTime();

      // If dates are different, sort by date
      if (dateA !== dateB) {
        return dateA - dateB;
      }

      // If dates are the same, use ID as a tiebreaker for stable ordering
      return a.id - b.id;
    });
  }, [documents]);

  if (!sortedDocuments.length) {
    return (
      <div className="bg-gray-100 p-2 text-sm text-gray-500 border-b">
        No hay documentos disponibles
      </div>
    );
  }

  return (
    <div className="flex justify-between items-center bg-gray-100 border-b">
      <div className="flex overflow-x-auto">
        {sortedDocuments.map((doc) => (
          <button
            key={doc.id}
            onClick={() => onSelectDocument(doc.id)}
            className={`px-4 py-2 min-w-[120px] text-sm font-medium whitespace-nowrap transition-colors
              ${
                activeDocumentId === doc.id
                  ? "bg-white text-blue-600 border-t-2 border-blue-600"
                  : "text-gray-600 hover:bg-gray-200"
              }`}
          >
            {getTabLabel(doc)}
          </button>
        ))}
      </div>

      {/* Display the document title in the tab bar */}
      {activeDocumentId && (
        <div className="px-4 text-sm font-medium text-gray-600">
          {getDocumentTitle(
            documents.find((doc) => doc.id === activeDocumentId)
          )}
        </div>
      )}
    </div>
  );
};

// Helper function to generate readable tab labels
function getTabLabel(doc: DocumentoOut): string {
  // Format the document type for display
  const typeLabels: Record<string, string> = {
    nota: "Nota Clínica",
    receta: "Receta Médica",
    laboratorio: "Órden Laboratorio",
    imagen: "Órden Imagen",
    certificado: "Certificado",
  };

  return typeLabels[doc.tipo.toLowerCase()] || `${doc.tipo}`;
}

// Helper function to get document title for display in the tab bar
function getDocumentTitle(doc?: DocumentoOut): string {
  if (!doc) return "";

  const typeLabels: Record<string, string> = {
    nota: "Nota Clínica",
    receta: "Receta Médica",
    laboratorio: "Órden de Laboratorio",
    imagen: "Órden de Imagen",
    certificado: "Certificado Médico",
  };

  const docType = typeLabels[doc.tipo.toLowerCase()] || doc.tipo;
  const date = new Date(doc.fecha_creacion).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return `${docType} - ${date}`;
}

export default TabBar;
