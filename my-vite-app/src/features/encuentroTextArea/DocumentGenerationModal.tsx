import React from "react";
import Modal from "@/commons/components/Modal";

interface Plantilla {
  id: number;
  nombre: string;
  tipo_documento: string;
  fecha_creacion: string;
  es_base: boolean;
  veces_usada: number;
  ultimo_uso: string | null;
}

interface DocumentGenerationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onGenerate: () => Promise<any>; // Changed type to return Promise
  isGenerating: boolean;
  error: string | null;
  plantillas: Plantilla[];
  isLoadingPlantillas: boolean;
  plantillasError: string | null;
  selectedPlantillaId: number | null;
  setSelectedPlantillaId: (id: number) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  generationStatus?: {
    inProgress: boolean;
    content: string;
    isComplete: boolean;
    error: string | null;
  };
}

const DocumentGenerationModal: React.FC<DocumentGenerationModalProps> = ({
  isOpen,
  onClose,
  onGenerate,
  isGenerating,
  error,
  plantillas,
  isLoadingPlantillas,
  plantillasError,
  selectedPlantillaId,
  setSelectedPlantillaId,
  searchQuery,
  setSearchQuery,
}) => {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Generar documentación médica"
      primaryButtonText="Generar"
      onPrimaryAction={onGenerate}
      isPrimaryDisabled={isGenerating || !selectedPlantillaId}
    >
      <div className="space-y-4">
        {/* Search bar for plantillas */}
        <div>
          <label
            htmlFor="search-plantillas"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Buscar plantillas
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
              <svg
                className="w-4 h-4 text-gray-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            </div>
            <input
              id="search-plantillas"
              type="search"
              className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              placeholder="Buscar por nombre..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        {/* Plantillas selection */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Seleccionar plantilla
          </label>
          <div className="border border-gray-300 rounded-md overflow-hidden max-h-64 overflow-y-auto">
            {isLoadingPlantillas ? (
              <div className="flex items-center justify-center p-4">
                <div className="animate-spin rounded-full h-5 w-5 border-t-2 border-b-2 border-blue-600 mr-2"></div>
                <span className="text-sm text-gray-600">
                  Cargando plantillas...
                </span>
              </div>
            ) : plantillasError ? (
              <div className="p-4 bg-red-50 text-red-700 text-sm">
                {plantillasError}
              </div>
            ) : plantillas.length === 0 ? (
              <div className="p-4 text-sm text-gray-500 text-center">
                {searchQuery
                  ? "No se encontraron plantillas con ese nombre"
                  : "No hay plantillas disponibles"}
              </div>
            ) : (
              <div className="divide-y divide-gray-200">
                {plantillas.map((plantilla) => {
                  const isSelected = selectedPlantillaId === plantilla.id;
                  return (
                    <div
                      key={plantilla.id}
                      className={`p-3 cursor-pointer transition-colors duration-150 ${
                        isSelected
                          ? "bg-blue-100 border-l-4 border-blue-500"
                          : "hover:bg-gray-50 border-l-4 border-transparent"
                      }`}
                      onClick={() => setSelectedPlantillaId(plantilla.id)}
                      role="option"
                      aria-selected={isSelected}
                      tabIndex={0}
                    >
                      <div className="flex items-center">
                        <span
                          className={`block text-sm font-medium ${
                            isSelected ? "text-blue-700" : "text-gray-700"
                          }`}
                        >
                          {plantilla.nombre}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-gray-500">
                        <span className="mr-3">{plantilla.tipo_documento}</span>
                        <span>
                          {plantilla.es_base
                            ? "Plantilla base"
                            : `Usada ${plantilla.veces_usada} veces`}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
};

export default DocumentGenerationModal;
