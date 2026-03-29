/**
 * Props for the TimerDisplay component
 */
export interface TimerDisplayProps {
  /** Duration in seconds to display */
  duration: number;
}

/**
 * Props for the MicrophoneIcon component
 */
export interface MicrophoneIconProps {
  /** Whether the microphone is actively recording */
  isRecording: boolean;
  /** Whether recording is paused */
  isPaused?: boolean;
}

/**
 * Props for the StartStopButton component
 */
export interface StartStopButtonProps {
  /** Whether recording is in progress */
  isRecording: boolean;
  /** Function to toggle recording state */
  onClick: () => void;
}

/**
 * Props for the PauseResumeButton component
 */
export interface PauseResumeButtonProps {
  /** Whether recording is in progress */
  isRecording: boolean;
  /** Whether recording is paused */
  isPaused: boolean;
  /** Function to toggle pause/resume state */
  onClick: () => void;
}

/**
 * Props for the DeleteButton component
 */
export interface DeleteButtonProps {
  /** Function to delete the current recording */
  onClick: () => void;
}

/**
 * Props for the PatientInfo component in TopBar
 */
export interface PatientInfoProps {
  /** Name of the encounter to display */
  encounterName: string;
  /** Formatted date of the encounter */
  encounterDate: string;
  /** Function to handle edit button click */
  onEdit: () => void;
}

/**
 * Props for the PatientEditModal component
 */
export interface PatientEditModalProps {
  /** Whether the modal is currently open */
  isOpen: boolean;
  /** Function to close the modal */
  onClose: () => void;
  /** Function called when a patient is selected */
  onSelectPatient: (patientId: number, patientName: string) => void;
  /** Function called when a new patient is created */
  onCreatePatient: (patientName: string) => void;
  /** Whether a patient is already connected to this encounter */
  isPatientConnected?: boolean;
  /** Current name of the encounter */
  currentEncounterName?: string;
  /** Current patient ID if a patient is connected */
  currentPatientId?: number | null;
  /** Current patient name if a patient is connected */
  currentPatientName?: string;
  /** Function to update both patient and encounter names */
  onUpdatePatientAndEncounter?: (
    patientId: number,
    patientName: string,
    encounterName: string
  ) => void;
}

/**
 * Props for the TopBar component
 */
export interface TopBarProps {
  /** Current name of the encounter */
  encounterName?: string;
  /** Formatted date of the encounter */
  encounterDate?: string;
  /** Function to update patient information */
  onUpdatePatient?: (patientId: number, patientName: string) => void;
  /** Whether the component is in updating state */
  isUpdating?: boolean;
}
