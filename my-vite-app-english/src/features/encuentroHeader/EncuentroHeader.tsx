import React from "react";
import { useParams } from "react-router-dom";
import PatientInfo from "./subcomponents/PatientInfo";
import VoiceRecorder from "./subcomponents/VoiceRecorder";
import PatientEditModal from "./PatientEditModal";
import Modal from "@/commons/components/Modal";
import GenerateDocumentationButton from "./subcomponents/GenerateDocumentationButton";

// Import context hooks
import { useTranscriptionContext } from "../../contexts/TranscriptionContext";
import { useGenerationContext } from "../../contexts/GenerationContext";
import { useEncuentroHeader } from "./hooks/useEncuentroHeader";

/**
 * EncuentroHeader component for the encounter page
 *
 * Displays patient information, recording controls, and handles
 * the modal for patient/encounter editing
 *
 * @returns React component
 */
const EncuentroHeader: React.FC = () => {
  // Get ID from URL
  const { id } = useParams<{ id: string }>();
  const encounterId = id ? parseInt(id, 10) : 0;

  // Use contexts
  const { hasBeenTranscribed } = useTranscriptionContext();
  const { openGenerationModal } = useGenerationContext();

  // Use the hook with the encounter ID
  const {
    // Modal states
    isModalOpen,
    isUnlinkModalOpen,
    isDeleteModalOpen,
    deleteErrorMessage,
    deleteSuccess,
    redirectInfo,
    progressPercentage,

    // Current encounter data
    encounterName,
    encounterDate,
    isPatientConnected,
    patientId,
    patientName,
    originalEncounterDateString,

    // Status
    isEncounterUpdating,
    isDateUpdating,

    // Methods
    setIsModalOpen,
    setIsUnlinkModalOpen,
    setIsDeleteModalOpen,
    handleEditClick,
    handleSelectPatient,
    handleCreatePatient,
    handleUpdatePatientAndEncounter,
    handleUnlinkClick,
    handleUnlinkConfirm,
    handleDeleteClick,
    handleDeleteConfirm,
    updateEncounterDate,
  } = useEncuentroHeader(encounterId);

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
              onUpdateDate={updateEncounterDate}
              isPatientConnected={isPatientConnected}
              onUnlink={handleUnlinkClick}
              onDelete={handleDeleteClick}
              originalDateString={originalEncounterDateString}
              isDateUpdating={isDateUpdating}
            />
            {isEncounterUpdating && (
              <div className="ml-3 inline-block animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-purple-500"></div>
            )}
          </div>

          <div className="flex items-center">
            {/* Generate Documentation Button - Now using context */}
            <div className="mr-4">
              <GenerateDocumentationButton />
            </div>

            {/* VoiceRecorder now uses context directly */}
            <VoiceRecorder />
          </div>
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
        title="Unlink Patient"
        primaryButtonText="Unlink"
        onPrimaryAction={handleUnlinkConfirm}
        isPrimaryDestructive={true}
      >
        <p>
          Are you sure you want to unlink the patient from this encounter? This
          action cannot be undone.
        </p>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={isDeleteModalOpen}
        onClose={() => {
          if (!deleteSuccess) {
            setIsDeleteModalOpen(false);
          }
        }}
        title={deleteSuccess ? "Encounter deleted" : "Delete encounter"}
        primaryButtonText={deleteSuccess ? undefined : "Delete"}
        onPrimaryAction={deleteSuccess ? undefined : handleDeleteConfirm}
        isPrimaryDestructive={!deleteSuccess}
      >
        <div>
          {!deleteSuccess && (
            <p className="mb-4">
              Are you sure you want to delete this encounter? This action cannot
              be undone and all associated data will be lost.
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
                Encounter deleted successfully!
              </p>
              <p className="mb-4">
                Redirecting to{" "}
                <span className="font-medium">
                  {redirectInfo.name === "Encuentro Nuevo"
                    ? "New Encounter"
                    : redirectInfo.name}
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
