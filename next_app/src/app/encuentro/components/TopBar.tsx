import React, { useState } from "react";
import Image from "next/image";
import {
  TimerDisplayProps,
  MicrophoneIconProps,
  StartStopButtonProps,
  DeleteButtonProps,
  PatientInfoProps,
} from "../utils/TopBarInterface";
import { useVoiceRecorder, formatTime } from "../utils/useTopBar";
import PatientEditModal from "./PatientEditModal";

// ========== SUBCOMPONENTS ==========
/**
 * Displays patient or encounter information with an edit button
 */
const PatientInfo: React.FC<PatientInfoProps> = ({
  encounterName,
  encounterDate,
  onEdit,
}) => (
  <div className="flex flex-col">
    <div className="flex items-center space-x-2">
      <span className="text-black font-medium">{encounterName}</span>
      <button
        onClick={onEdit}
        className="text-gray-500 hover:text-purple-600 focus:outline-none"
        aria-label="Edit patient"
        title="Editar paciente o encuentro"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
          />
        </svg>
      </button>
    </div>
    <span className="text-xs text-gray-500">{encounterDate}</span>
  </div>
);

/**
 * Displays the recording timer
 */
const TimerDisplay: React.FC<TimerDisplayProps> = ({ duration }) => (
  <div className="flex items-center space-x-2">
    <Image
      src="/clock.svg"
      alt="Timer"
      width={24}
      height={24}
      className="text-gray-500"
    />
    <span className="text-black font-mono">{formatTime(duration)}</span>
  </div>
);

/**
 * Displays microphone status icon
 */
const MicrophoneIcon: React.FC<MicrophoneIconProps> = ({ isRecording }) => (
  <Image
    src={isRecording ? "/microphone_on.svg" : "/microphone_off.svg"}
    alt="Microphone status"
    width={24}
    height={24}
    className={isRecording ? "text-red-500" : "text-gray-500"}
  />
);

/**
 * Button to start or stop recording
 */
const StartStopButton: React.FC<StartStopButtonProps> = ({
  isRecording,
  onClick,
}) => (
  <button
    onClick={onClick}
    className={`px-4 py-2 rounded-md text-white font-medium transition-colors ${
      isRecording
        ? "bg-red-500 hover:bg-red-600"
        : "bg-purple-500 hover:bg-purple-600"
    }`}
  >
    {isRecording ? "Stop" : "Start"} Recording
  </button>
);

/**
 * Button to delete the current recording
 */
const DeleteButton: React.FC<DeleteButtonProps> = ({ onClick }) => (
  <button
    onClick={onClick}
    className="px-4 py-2 rounded-md bg-gray-200 text-black font-medium hover:bg-gray-300 transition-colors"
  >
    Delete
  </button>
);

/**
 * Settings icon button
 */
const SettingsIcon: React.FC = () => (
  <Image
    src="/settings.svg"
    alt="Settings"
    width={24}
    height={24}
    className="text-gray-500 hover:text-gray-700 cursor-pointer"
  />
);

/**
 * Voice recorder component with controls
 */
const VoiceRecorder: React.FC = () => {
  const {
    isRecording,
    duration,
    startRecording,
    stopRecording,
    deleteRecording,
  } = useVoiceRecorder();

  return (
    <div className="flex items-center space-x-4">
      <TimerDisplay duration={duration} />
      <MicrophoneIcon isRecording={isRecording} />
      <StartStopButton
        isRecording={isRecording}
        onClick={isRecording ? stopRecording : startRecording}
      />
      <DeleteButton onClick={deleteRecording} />
      <SettingsIcon />
    </div>
  );
};

// ========== MAIN COMPONENT ==========
/**
 * Props for the TopBar component
 */
interface TopBarProps {
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
  patientId?: number;
  /** Name of the connected patient if any */
  patientName?: string;
}

/**
 * TopBar component for the encounter page
 *
 * Displays patient information, recording controls, and handles
 * the modal for patient/encounter editing
 *
 * @param props - Component props
 * @returns React component
 */
const TopBar: React.FC<TopBarProps> = ({
  encounterName = "Consulta médica",
  encounterDate = "Sin fecha",
  onUpdatePatient = () => {},
  onUpdatePatientAndEncounter = () => {},
  isUpdating = false,
  isPatientConnected = false,
  patientId = 0,
  patientName = "",
}) => {
  // State to control modal visibility
  const [isModalOpen, setIsModalOpen] = useState(false);

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
            />
            {isUpdating && (
              <div className="ml-3 inline-block animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-purple-500"></div>
            )}
          </div>
          <VoiceRecorder />
        </div>
      </nav>

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
    </>
  );
};

export default TopBar;
