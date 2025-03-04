import React, { useState, useEffect } from "react";
import PatientInfo from "./subcomponents/PatientInfo";
import VoiceRecorder from "./subcomponents/VoiceRecorder";
import PatientEditModal from "../PatientEditModal";
import Modal from "../../../../components/Modal";
import { useEncounter } from "../../hooks/useEncounter";
import { useRouter } from "next/navigation";
import useEncuentroList from "../../../app_layout/hooks/Encuentros/useEncuentroList";

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
}) => {
  // State to control modals visibility
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isUnlinkModalOpen, setIsUnlinkModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [deleteErrorMessage, setDeleteErrorMessage] = useState<string | null>(
    null
  );

  // New states for success feedback
  const [deleteSuccess, setDeleteSuccess] = useState(false);
  const [redirectInfo, setRedirectInfo] = useState<{
    path: string;
    name: string;
  } | null>(null);
  const [redirectCountdown, setRedirectCountdown] = useState(0.5);
  const [progressPercentage, setProgressPercentage] = useState(0);

  // Get the current URL to extract the encounter ID
  const urlParts =
    typeof window !== "undefined" ? window.location.pathname.split("/") : [];
  const encounterIdFromUrl = parseInt(urlParts[urlParts.length - 1]);

  // Hook for encounter operations
  const {
    updateEncounter,
    deleteEncounter,
    isLoading: isEncounterUpdating,
  } = useEncounter(encounterIdFromUrl);

  // Hook for encounter list to get the first encounter for redirection
  const { encuentros } = useEncuentroList();

  // Router for navigation
  const router = useRouter();

  // Effect for countdown and redirect after successful deletion
  useEffect(() => {
    let countdownTimer: NodeJS.Timeout;
    let progressTimer: NodeJS.Timeout;

    if (deleteSuccess && redirectInfo) {
      // Handle the countdown (0.5 second)
      if (redirectCountdown > 0) {
        countdownTimer = setTimeout(() => {
          setRedirectCountdown(0);
        }, 500);
      } else {
        router.push(redirectInfo.path);
      }

      // Handle the progress bar animation (updates every 0.1 seconds - 5 updates total)
      if (progressPercentage < 100) {
        progressTimer = setTimeout(() => {
          setProgressPercentage((prev) => Math.min(prev + 20, 100));
        }, 100);
      }
    }

    return () => {
      if (countdownTimer) clearTimeout(countdownTimer);
      if (progressTimer) clearTimeout(progressTimer);
    };
  }, [
    deleteSuccess,
    redirectInfo,
    redirectCountdown,
    progressPercentage,
    router,
  ]);

  /**
   * Open the patient edit modal
   */
  const handleEditClick = () => {
    setIsModalOpen(true);
  };

  /**
   * Handle patient selection from modal
   */
  const handleSelectPatient = (patientId: number, patientName: string) => {
    console.log(`Selected patient: ID=${patientId}, Name=${patientName}`);
    onUpdatePatient(patientId, patientName);
  };

  /**
   * Handle patient creation from modal
   */
  const handleCreatePatient = (patientName: string) => {
    console.log(`New patient created: ${patientName}`);
    // The actual update is handled in handleSelectPatient which is also called
  };

  /**
   * Handle updating both patient and encounter names
   */
  const handleUpdatePatientAndEncounter = (
    patientId: number,
    patientName: string,
    encounterName: string
  ) => {
    console.log(
      `Updating both patient and encounter: PatientID=${patientId}, PatientName=${patientName}, EncounterName=${encounterName}`
    );
    onUpdatePatientAndEncounter(patientId, patientName, encounterName);
  };

  /**
   * Opens the unlink confirmation modal
   */
  const handleUnlinkClick = () => {
    setIsUnlinkModalOpen(true);
  };

  /**
   * Handles the patient unlinking process
   * Removes the patient connection from the encounter
   */
  const handleUnlinkConfirm = async () => {
    // Get the encounter ID from URL or props
    const urlParts = window.location.pathname.split("/");
    const encounterIdFromUrl = parseInt(urlParts[urlParts.length - 1]);

    const success = await updateEncounter(encounterIdFromUrl, {
      paciente_conectado: false,
      id_paciente: null, // Use undefined instead of null
      nombre_encuentro: "Encuentro Nuevo", // Reset encounter name
    });

    if (success) {
      // Update local state - this would typically trigger a page refresh or state update
      console.log("Patient unlinked successfully");
      // Here you would update local state or refresh the page
      window.location.reload(); // Simple reload for now
    }

    setIsUnlinkModalOpen(false);
  };

  /**
   * Opens the delete confirmation modal
   */
  const handleDeleteClick = () => {
    setIsDeleteModalOpen(true);
    setDeleteErrorMessage(null);
  };

  /**
   * Handles the encounter deletion process
   */
  const handleDeleteConfirm = async () => {
    const result = await deleteEncounter();

    if (result.success) {
      console.log("Encounter deleted successfully");
      setDeleteSuccess(true);
      setProgressPercentage(0); // Reset progress percentage

      // Determine where to redirect
      if (encuentros.length > 0) {
        // Find the first encounter that is not the current one
        const nextEncounter = encuentros.find(
          (e) => e.id !== encounterIdFromUrl
        );

        if (nextEncounter) {
          setRedirectInfo({
            path: `/encuentro/${nextEncounter.id}`,
            name: nextEncounter.nombre_encuentro,
          });
        } else {
          setRedirectInfo({
            path: "/dashboard",
            name: "Panel Principal",
          });
        }
      } else {
        setRedirectInfo({
          path: "/dashboard",
          name: "Panel Principal",
        });
      }
    } else {
      // Handle deletion error
      setDeleteErrorMessage(
        "Error al eliminar el encuentro. Por favor intente nuevamente."
      );
      console.error("Error deleting encounter:", result);
    }
  };

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
          <VoiceRecorder />
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
          ¿Estás seguro de que deseas desconectar el paciente de este encuentro?
          Esta acción no puede deshacerse.
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
        title={deleteSuccess ? "Encuentro eliminado" : "Eliminar encuentro"}
        primaryButtonText={deleteSuccess ? undefined : "Eliminar"}
        onPrimaryAction={deleteSuccess ? undefined : handleDeleteConfirm}
        isPrimaryDestructive={!deleteSuccess}
      >
        <div>
          {!deleteSuccess && (
            <p className="mb-4">
              ¿Estás seguro de que deseas eliminar este encuentro? Esta acción
              no puede deshacerse y se perderán todos los datos asociados.
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
                <span className="font-medium">{redirectInfo.name}</span>...
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
            <p className="text-red-500 mt-2">{deleteErrorMessage}</p>
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
