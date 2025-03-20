import React from "react";
import PatientInfo from "./subcomponents/PatientInfo";
import VoiceRecorder from "./subcomponents/VoiceRecorder";
import PatientEditModal from "./PatientEditModal";
import Modal from "../../components/Modal";
import { useEncuentroHeader } from "./hooks/useEncuentroHeader";

/**
 * Props for the EncuentroHeader component
 */
interface EncuentroHeaderProps {
    /** Name of the encounter to display */
    encounterName?: string;
    /** Formatted date of the encounter */
    encounterDate?: string;
    /** Function to update patient information */
    onUpdatePatient?: (patientId: number, patientName: string) => void;
    /** Function to update both patient and encounter information */
    onUpdatePatientAndEncounter?: (
        patientId: number,
        patientName: string,
        encounterName: string
    ) => void;
    /** Whether an update operation is in progress */
    isUpdating?: boolean;
    /** Whether a patient is connected to this encounter */
    isPatientConnected?: boolean;
    /** ID of the connected patient if any */
    patientId?: number | null;
    /** Name of the connected patient if any */
    patientName?: string;
    /** ID of the transcription document if available */
    transcriptionDocId?: number;
}

/**
 * EncuentroHeader component for the encounter page
 *
 * Displays patient information, recording controls, and handles
 * the modal for patient/encounter editing
 *
 * @param props - Component props
 * @returns React component
 */
const EncuentroHeader: React.FC<EncuentroHeaderProps> = ({
    encounterName = "Consulta médica",
    encounterDate = "Sin fecha",
    onUpdatePatient = () => {},
    onUpdatePatientAndEncounter = () => {},
    isUpdating = false,
    isPatientConnected = false,
    patientId = null,
    patientName = "",
    transcriptionDocId,
}) => {
    // Get the current URL to extract the encounter ID
    const urlParts =
        typeof window !== "undefined"
            ? window.location.pathname.split("/")
            : [];
    const encounterIdFromUrl = parseInt(urlParts[urlParts.length - 1]) || 0;

    // Use our custom hook with fixed parameter order
    const {
        // Modal states
        isModalOpen,
        isUnlinkModalOpen,
        isDeleteModalOpen,
        deleteErrorMessage,
        deleteSuccess,
        redirectInfo,
        progressPercentage,

        // Modal actions
        setIsModalOpen,
        setIsUnlinkModalOpen,
        setIsDeleteModalOpen,

        // Event handlers
        handleEditClick,
        handleSelectPatient,
        handleCreatePatient,
        handleUpdatePatientAndEncounter,
        handleUnlinkClick,
        handleUnlinkConfirm,
        handleDeleteClick,
        handleDeleteConfirm,

        // Status
        isEncounterUpdating,
    } = useEncuentroHeader(
        encounterIdFromUrl,
        onUpdatePatient,
        onUpdatePatientAndEncounter,
        transcriptionDocId
    );

    return (
        <>
            <nav
                className="sticky top-0 w-full bg-white border-t border-b border-blue-200 shadow-sm z-10"
                data-testid="encounter-topbar"
            >
                <div className="flex justify-between items-center px-6 py-3">
                    <div className="flex items-center">
                        <PatientInfo
                            encounterName={encounterName}
                            encounterDate={encounterDate}
                            onEdit={handleEditClick}
                            isPatientConnected={isPatientConnected}
                            onUnlink={handleUnlinkClick}
                            onDelete={handleDeleteClick}
                        />
                        {isUpdating && (
                            <div className="ml-3 inline-block animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-purple-500"></div>
                        )}
                    </div>
                    <VoiceRecorder transcriptionDocId={transcriptionDocId} />
                </div>
            </nav>

            {/* Patient Edit Modal */}
            <PatientEditModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                onSelectPatient={handleSelectPatient}
                onCreatePatient={handleCreatePatient}
                isPatientConnected={isPatientConnected}
                currentEncounterName={encounterName}
                currentPatientId={patientId}
                currentPatientName={patientName}
                onUpdatePatientAndEncounter={handleUpdatePatientAndEncounter}
            />

            {/* Unlink Confirmation Modal */}
            <Modal
                isOpen={isUnlinkModalOpen}
                onClose={() => setIsUnlinkModalOpen(false)}
                title="Desconectar paciente"
                primaryButtonText="Desconectar"
                onPrimaryAction={handleUnlinkConfirm}
                isPrimaryDestructive={true}
            >
                <p>
                    ¿Estás seguro de que deseas desconectar el paciente de este
                    encuentro? Esta acción no puede deshacerse.
                </p>
            </Modal>

            {/* Delete Confirmation Modal */}
            <Modal
                isOpen={isDeleteModalOpen}
                onClose={() => {
                    if (!deleteSuccess) {
                        setIsDeleteModalOpen(false);
                    }
                    // Don't allow closing if delete was successful - must wait for redirect
                }}
                title={
                    deleteSuccess ? "Encuentro eliminado" : "Eliminar encuentro"
                }
                primaryButtonText={deleteSuccess ? undefined : "Eliminar"}
                onPrimaryAction={
                    deleteSuccess ? undefined : handleDeleteConfirm
                }
                isPrimaryDestructive={!deleteSuccess}
            >
                <div>
                    {!deleteSuccess && (
                        <p className="mb-4">
                            ¿Estás seguro de que deseas eliminar este encuentro?
                            Esta acción no puede deshacerse y se perderán todos
                            los datos asociados.
                        </p>
                    )}

                    {deleteSuccess && redirectInfo && (
                        <div className="text-center">
                            <div className="mb-2 flex justify-center">
                                <svg
                                    className="w-16 h-16 text-green-500"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                    xmlns="http://www.w3.org/2000/svg"
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth="2"
                                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                                    ></path>
                                </svg>
                            </div>
                            <p className="text-lg font-medium mb-2">
                                ¡Encuentro eliminado con éxito!
                            </p>
                            <p className="mb-4">
                                Redirigiendo a{" "}
                                <span className="font-medium">
                                    {redirectInfo.name}
                                </span>
                                ...
                            </p>
                            <div className="bg-gray-200 h-1 rounded-full max-w-xs mx-auto">
                                <div
                                    className="bg-purple-500 h-1 rounded-full transition-all duration-100"
                                    style={{ width: `${progressPercentage}%` }}
                                ></div>
                            </div>
                        </div>
                    )}

                    {deleteErrorMessage && (
                        <p className="text-red-500 mt-2">
                            {deleteErrorMessage}
                        </p>
                    )}

                    {isEncounterUpdating && (
                        <div className="flex justify-center my-2">
                            <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-purple-500"></div>
                        </div>
                    )}
                </div>
            </Modal>
        </>
    );
};

export default EncuentroHeader;
