import React from "react";
import Modal from "@/components/Modal";

interface DocumentGenerationModalProps {
    isOpen: boolean;
    onClose: () => void;
    onGenerate: () => Promise<string | null>;
    isGenerating: boolean;
    error: string | null;
}

const DocumentGenerationModal: React.FC<DocumentGenerationModalProps> = ({
    isOpen,
    onClose,
    onGenerate,
    isGenerating,
    error,
}) => {
    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title="Generar documentación médica"
            primaryButtonText="Generar"
            onPrimaryAction={onGenerate}
            isPrimaryDisabled={isGenerating}
        >
            <div className="space-y-4">
                <p>
                    Esta acción generará automáticamente la documentación médica
                    basada en la transcripción de la consulta y el contexto del
                    paciente.
                </p>

                <div className="bg-blue-50 p-3 rounded-md border border-blue-200">
                    <p className="text-blue-700 text-sm">
                        <strong>Nota:</strong> El sistema analizará la
                        conversación transcrita y creará una nota clínica
                        estructurada según las mejores prácticas médicas.
                    </p>
                </div>

                {isGenerating && (
                    <div className="flex items-center justify-center space-x-2">
                        <div className="animate-spin rounded-full h-5 w-5 border-t-2 border-b-2 border-blue-600"></div>
                        <span className="text-blue-600 font-medium">
                            Generando documentación...
                        </span>
                    </div>
                )}

                {error && (
                    <div className="bg-red-50 p-3 rounded-md border border-red-200">
                        <p className="text-red-700 text-sm">{error}</p>
                    </div>
                )}
            </div>
        </Modal>
    );
};

export default DocumentGenerationModal;
