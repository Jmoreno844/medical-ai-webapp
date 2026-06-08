import React from "react";
import PatientInfo from "./subcomponents/PatientInfo";
import VoiceRecorder from "./subcomponents/VoiceRecorder";
import PatientEditModal from "./PatientEditModal";
import Modal from "@/commons/components/Modal";
import GenerateDocumentationButton from "./subcomponents/GenerateDocumentationButton";
import TranscribeButton from "./subcomponents/TranscribeButton";

import { useEncuentroContext } from "../../contexts/EncuentroContext";
import { useTranscriptionContext } from "../../contexts/TranscriptionContext";
import { useGenerationContext } from "../../contexts/GenerationContext";
import { useAuth } from "@/commons/hooks/useAuth";
import { resolveEncounterActivityStatus } from "./resolveEncounterActivityStatus";

/**
 * EncuentroHeader component for the encounter page
 *
 * Displays patient information, recording controls, and handles
 * the modal for patient/encounter editing
 *
 * @returns React component
 */
const EncuentroHeaderContent: React.FC = () => {
  // Use the encounter context instead of the hook
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
    encounterId, // <<< Get encounterId from context
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
    updateEncounterName,
    linkPatientToEncounter,
    createAndLinkPatient,
    updateLinkedPatientName,
    deleteLinkedPatient,
    handleUnlinkConfirm,
    handleDeleteClick,
    handleDeleteConfirm,
    updateEncounterDate,
  } = useEncuentroContext();
  const {
    isRecording,
    isPaused,
    pendingAudioSections,
    isTranscribing,
    transcriptionStatus,
    canRetryTranscription,
  } = useTranscriptionContext();
  const { isGenerating, generationStatus } = useGenerationContext();
  const { capabilities, userData } = useAuth();
  const canUseClinicalFeatures = capabilities.can_use_clinical_features;
  const showClinicalAccessWarning =
    userData !== null && !canUseClinicalFeatures;

  const activityStatus = resolveEncounterActivityStatus({
    isRecording,
    isPaused,
    pendingAudioSections,
    isTranscribing,
    transcriptionStatus,
    isGenerating,
    generationError: generationStatus.error,
  });

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
              onOpenPatientModal={handleEditClick}
              onUpdateEncounterName={updateEncounterName}
              onSelectPatient={linkPatientToEncounter}
              onCreateAndLinkPatient={createAndLinkPatient}
              onUpdateDate={updateEncounterDate}
              isPatientConnected={isPatientConnected}
              onDelete={handleDeleteClick}
              originalDateString={originalEncounterDateString}
              isDateUpdating={isDateUpdating}
            />
            {isEncounterUpdating && (
              <div className="ml-3 inline-block animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-purple-500"></div>
            )}
          </div>

          <div className="flex items-center">
            {activityStatus.showBadge && (
              <div
                className={`mr-4 flex items-center gap-2 text-[15px] ${activityStatus.textClassName}`}
              >
                <span className="relative flex h-2.5 w-2.5">
                  {activityStatus.showPing && (
                    <span
                      className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${activityStatus.pingClassName}`}
                    />
                  )}
                  <span
                    className={`relative inline-flex h-2.5 w-2.5 rounded-full ${activityStatus.dotClassName}`}
                  />
                </span>
                <span className="font-medium">{activityStatus.label}</span>
              </div>
            )}

            <div className="mr-4 flex items-center gap-2">
              {canRetryTranscription && <TranscribeButton />}
              <GenerateDocumentationButton />
            </div>

            {/* VoiceRecorder now uses context directly and gets a key */}
            <VoiceRecorder key={encounterId} /> {/* <<< Add key prop */}
          </div>
        </div>
        {showClinicalAccessWarning ? (
          <div className="border-t border-amber-200 bg-amber-50 px-6 py-2 text-sm text-amber-900">
            Tu cuenta no tiene acceso clínico activo. Puedes revisar el
            encuentro, pero la transcripción y la generación de documentos están
            deshabilitadas. Contacta al administrador.
          </div>
        ) : null}
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
        onUpdatePatient={updateLinkedPatientName}
        onUnlinkEncounter={handleUnlinkConfirm}
        onDeletePatient={deleteLinkedPatient}
        isUpdating={isEncounterUpdating}
      />

      {/* Unlink Confirmation Modal */}
      <Modal
        isOpen={isUnlinkModalOpen}
        onClose={() => setIsUnlinkModalOpen(false)}
        title="Desvincular paciente"
        primaryButtonText="Desvincular"
        onPrimaryAction={handleUnlinkConfirm}
        isPrimaryDestructive={true}
      >
        <p>
          ¿Seguro que desea desvincular al paciente de este encuentro? Esta acción
          no se puede deshacer.
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
        title={deleteSuccess ? "Encuentro eliminado" : "Eliminar encuentro"}
        primaryButtonText={deleteSuccess ? undefined : "Eliminar"}
        onPrimaryAction={deleteSuccess ? undefined : handleDeleteConfirm}
        isPrimaryDestructive={!deleteSuccess}
      >
        <div>
          {!deleteSuccess && (
            <p className="mb-4">
              ¿Seguro que desea eliminar este encuentro? No podrá deshacerlo y se
              perderán los datos asociados.
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
                ¡Encuentro eliminado correctamente!
              </p>
              <p className="mb-4">
                Redirigiendo a{" "}
                <span className="font-medium">
                  {redirectInfo.name === "Encuentro Nuevo"
                    ? "Nuevo encuentro"
                    : redirectInfo.name}
                </span>
                …
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

/**
 * Header uses EncuentroProvider from AppProviders (single source of truth).
 */
const EncuentroHeader: React.FC = () => <EncuentroHeaderContent />;

export default EncuentroHeader;
