import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import * as encountersApi from "@/api/encounters";
import { useNavigate } from "react-router-dom";
import { useVoiceRecorder } from "../features/encuentroHeader/hooks/audio/useVoiceRecorder";
import { useEncounter } from "../features/encuentro/hooks/useEncounter";
import useEncuentroList from "../features/app_layout/hooks/Encuentros/useEncuentroList";
import { logger } from "@/lib/logger";

// Define the Encuentro interface if it's not imported
export interface Encuentro {
  id: number;
  encounter_name: string;
  occurred_at: string;
  patient_id?: number;
  patient_name?: string;
  patient_connected?: boolean;
  has_been_transcribed?: boolean;
}

// Add this date formatting helper function
const formatDate = (dateString: string): string => {
  try {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat("es", {
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } catch (error) {
    logger.error("Error formatting date:", error);
    return "Sin fecha";
  }
};

/**
 * EncuentroContext provides data and functionality for managing medical encounters
 */
type EncuentroContextType = {
  /** Current encounter id from the provider (for keys, recorder, etc.) */
  encounterId: number;

  // ---- Base encounter state ----
  encuentro: Encuentro | null;
  isLoading: boolean;
  error: string | null;

  // ---- Base encounter actions ----
  updateEncuentro: (data: Partial<Encuentro>) => Promise<boolean>;
  refetch: () => Promise<void>;

  // ---- EncuentroHeader specific functionality ----
  // Modal states
  isModalOpen: boolean;
  isUnlinkModalOpen: boolean;
  isDeleteModalOpen: boolean;
  deleteErrorMessage: string | null;
  deleteSuccess: boolean;
  redirectInfo: { path: string; name: string } | null;
  progressPercentage: number;

  // Encounter data
  encounterName: string;
  encounterDate: string;
  originalEncounterDateString: string | null;
  isPatientConnected: boolean;
  patientId: number | null;
  patientName: string;

  // Status indicators
  isEncounterUpdating: boolean;
  isDateUpdating: boolean;

  // Modal actions
  setIsModalOpen: (isOpen: boolean) => void;
  setIsUnlinkModalOpen: (isOpen: boolean) => void;
  setIsDeleteModalOpen: (isOpen: boolean) => void;

  // Event handlers
  handleEditClick: () => void;
  handleSelectPatient: (
    patientId: number,
    patientName: string
  ) => Promise<void>;
  handleCreatePatient: (patientName: string) => void;
  handleUpdatePatientAndEncounter: (
    patientId: number,
    patientName: string,
    encounterName: string
  ) => Promise<void>;
  handleUnlinkClick: () => void;
  handleUnlinkConfirm: () => Promise<void>;
  handleDeleteClick: () => void;
  handleDeleteConfirm: () => Promise<void>;
  updateEncounterDate: (date: Date) => Promise<boolean>;

  // Voice recorder
  voiceRecorder: ReturnType<typeof useVoiceRecorder>;
};

const EncuentroContext = createContext<EncuentroContextType | undefined>(
  undefined
);

export function EncuentroProvider({
  children,
  encounterId,
  transcriptionDocId,
}: {
  children: React.ReactNode;
  encounterId: number;
  transcriptionDocId?: number;
}) {
  // Navigate hook for redirection
  const navigate = useNavigate();

  // ---- Base encounter state from original context ----
  const [encuentro, setEncuentro] = useState<Encuentro | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // ---- State from useEncuentroHeader ----
  // Modal states
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isUnlinkModalOpen, setIsUnlinkModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [deleteErrorMessage, setDeleteErrorMessage] = useState<string | null>(
    null
  );
  const [deleteSuccess, setDeleteSuccess] = useState(false);
  const [redirectInfo, setRedirectInfo] = useState<{
    path: string;
    name: string;
  } | null>(null);
  const [redirectCountdown, setRedirectCountdown] = useState(0.5);
  const [progressPercentage, setProgressPercentage] = useState(0);

  // Encounter data
  const [encounterName, setEncounterName] = useState("Consulta médica");
  const [encounterDate, setEncounterDate] = useState("Sin fecha");
  const [originalEncounterDateString, setOriginalEncounterDateString] =
    useState<string | null>(null);
  const [isPatientConnected, setIsPatientConnected] = useState(false);
  const [patientId, setPatientId] = useState<number | null>(null);
  const [patientName, setPatientName] = useState("");
  const [isDateUpdating, setIsDateUpdating] = useState(false);

  // Hooks
  const { encuentros } = useEncuentroList();
  const {
    updateEncounter,
    deleteEncounter,
    isLoading: isEncounterUpdating,
  } = useEncounter(encounterId);
  const voiceRecorder = useVoiceRecorder(encounterId, transcriptionDocId);

  // Fetch data function
  const fetchData = useCallback(async () => {
    if (!encounterId) {
      setError("ID no válido");
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    logger.debug(`Fetching encounter data for ID: ${encounterId}`);

    try {
      const response = await encountersApi.getEncounter(encounterId);
      logger.debug("Encounter data received:", response.data);
      setEncuentro(response.data);

      // Update local state with fetched data
      if (response.data) {
        const data = response.data;
        if (data.encounter_name) {
          setEncounterName(data.encounter_name);
        }

        if (data.occurred_at) {
          setEncounterDate(formatDate(data.occurred_at));
          setOriginalEncounterDateString(data.occurred_at);
        }

        setIsPatientConnected(!!data.patient_connected);

        if (data.patient_connected) {
          setPatientId(data.patient_id || null);
          setPatientName(data.patient_name || "");
        } else {
          setPatientId(null);
          setPatientName("");
        }
      }
    } catch (err: any) {
      const errorMsg =
        err.response?.data?.message || err.message || "Error desconocido";
      setError(errorMsg);
      logger.error("Error fetching encounter:", errorMsg, err);
    } finally {
      setIsLoading(false);
    }
  }, [encounterId]);

  // Initial data fetch
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Effect for countdown and redirect after successful deletion
  useEffect(() => {
    let countdownTimer: ReturnType<typeof setTimeout> | undefined;
    let progressTimer: ReturnType<typeof setTimeout> | undefined;

    if (deleteSuccess && redirectInfo) {
      if (redirectCountdown > 0) {
        countdownTimer = setTimeout(() => {
          setRedirectCountdown(0);
        }, 500);
      } else {
        logger.debug(`Attempting navigation to: ${redirectInfo.path}`);
        try {
          navigate(redirectInfo.path, { replace: true });
          setTimeout(() => {
            if (
              window.location.pathname.includes(`/encuentro/${encounterId}`)
            ) {
              logger.debug(`Using fallback navigation to: ${redirectInfo.path}`);
              window.location.href = redirectInfo.path;
            }
          }, 200);
        } catch (err) {
          logger.error("Navigation error:", err);
          window.location.href = redirectInfo.path;
        }
      }

      if (progressPercentage < 100) {
        progressTimer = setTimeout(() => {
          setProgressPercentage((prev) => Math.min(prev + 20, 100));
        }, 100);
      }
    }

    return () => {
      if (countdownTimer !== undefined) clearTimeout(countdownTimer);
      if (progressTimer !== undefined) clearTimeout(progressTimer);
    };
  }, [
    deleteSuccess,
    redirectInfo,
    redirectCountdown,
    progressPercentage,
    navigate,
    encounterId,
  ]);

  /**
   * Update encounter data through the API
   */
  const updateEncuentro = useCallback(
    async (data: Partial<Encuentro>): Promise<boolean> => {
      if (!encounterId) return false;

      try {
        logger.debug(
          `[ENCUENTRO] Updating encounter ${encounterId} with:`,
          data
        );
        const response = await axiosInstance.patch(
          `/api/v1/encounters/${encounterId}`,
          data
        );

        if (response.status === 200) {
          await fetchData();
          return true;
        }
        return false;
      } catch (error) {
        logger.error(`[ENCUENTRO] Error updating encounter:`, error);
        return false;
      }
    },
    [encounterId, fetchData]
  );

  // ---- Methods from useEncuentroHeader ----

  /**
   * Open the patient edit modal
   */
  const handleEditClick = useCallback(() => {
    setIsModalOpen(true);
  }, []);

  /**
   * Update encounter date in the database
   */
  const updateEncounterDate = useCallback(
    async (newDate: Date) => {
      try {
        setIsDateUpdating(true);
        const isoDate = newDate.toISOString();
        logger.debug(`Updating encounter date to: ${isoDate}`);

        const response = await axiosInstance.patch(
          `/api/v1/encounters/${encounterId}`,
          {
            occurred_at: isoDate,
          }
        );

        if (response.status === 200) {
          setEncounterDate(formatDate(isoDate));
          setOriginalEncounterDateString(isoDate);
          logger.debug("Encounter date updated successfully");
          return true;
        } else {
          logger.error("Failed to update encounter date:", response);
          return false;
        }
      } catch (error) {
        logger.error("Error updating encounter date:", error);
        return false;
      } finally {
        setIsDateUpdating(false);
      }
    },
    [encounterId]
  );

  /**
   * Handle patient selection from modal
   */
  const handleSelectPatient = useCallback(
    async (patientId: number, patientName: string) => {
      logger.debug(`Selected patient: ID=${patientId}, Name=${patientName}`);

      const success = await updateEncounter(encounterId, {
        patient_id: patientId,
        patient_connected: true,
        encounter_name: patientName,
      });

      if (success) {
        setEncounterName(patientName);
        setIsPatientConnected(true);
        setPatientId(patientId);
        setPatientName(patientName);
        setIsModalOpen(false);
      } else {
        logger.error("Failed to update patient connection");
      }
    },
    [encounterId, updateEncounter]
  );

  /**
   * Handle patient creation from modal
   */
  const handleCreatePatient = useCallback((patientName: string) => {
    logger.debug(`New patient created: ${patientName}`);
    // The actual update is handled in handleSelectPatient which is called after creation
  }, []);

  /**
   * Handle updating both patient and encounter names
   */
  const handleUpdatePatientAndEncounter = useCallback(
    async (patientId: number, patientName: string, encounterName: string) => {
      logger.debug(
        `Updating both patient and encounter: PatientID=${patientId}, PatientName=${patientName}, EncounterName=${encounterName}`
      );

      const success = await updateEncounter(encounterId, {
        patient_id: patientId,
        patient_connected: true,
        encounter_name: encounterName,
      });

      if (success) {
        setEncounterName(encounterName);
        setIsPatientConnected(true);
        setPatientId(patientId);
        setPatientName(patientName);
      } else {
        logger.error("Failed to update patient and encounter information");
      }
    },
    [encounterId, updateEncounter]
  );

  /**
   * Opens the unlink confirmation modal
   */
  const handleUnlinkClick = useCallback(() => {
    setIsUnlinkModalOpen(true);
  }, []);

  /**
   * Handles the patient unlinking process
   */
  const handleUnlinkConfirm = useCallback(async () => {
    const success = await updateEncounter(encounterId, {
      patient_connected: false,
      patient_id: null,
      encounter_name: "Encuentro Nuevo",
    });

    if (success) {
      logger.debug("Patient unlinked successfully");
      window.location.reload();
    }

    setIsUnlinkModalOpen(false);
  }, [encounterId, updateEncounter]);

  /**
   * Opens the delete confirmation modal
   */
  const handleDeleteClick = useCallback(() => {
    setIsDeleteModalOpen(true);
    setDeleteErrorMessage(null);
  }, []);

  /**
   * Handles the encounter deletion process
   */
  const handleDeleteConfirm = useCallback(async () => {
    const result = await deleteEncounter();

    if (result.success) {
      logger.debug("Encounter deleted successfully");
      setDeleteSuccess(true);
      setProgressPercentage(0);

      if (encuentros.length > 0) {
        const nextEncounter = encuentros.find((e) => e.id !== encounterId);

        if (nextEncounter) {
          setRedirectInfo({
            path: `/encuentro/${nextEncounter.id}`,
            name: nextEncounter.encounter_name,
          });
        } else {
          setRedirectInfo({
            path: "/home",
            name: "Panel Principal",
          });
        }
      } else {
        setRedirectInfo({
          path: "/home",
          name: "Panel Principal",
        });
      }
    } else {
      setDeleteErrorMessage(
        "Error al eliminar el encuentro. Por favor intente nuevamente."
      );
      logger.error("Error deleting encounter:", result);
    }
  }, [deleteEncounter, encuentros, encounterId]);

  // Context value
  const value: EncuentroContextType = {
    encounterId,

    // Base encounter state and actions
    encuentro,
    isLoading,
    error,
    updateEncuentro,
    refetch: fetchData,

    // Modal states
    isModalOpen,
    isUnlinkModalOpen,
    isDeleteModalOpen,
    deleteErrorMessage,
    deleteSuccess,
    redirectInfo,
    progressPercentage,

    // Encounter data
    encounterName,
    encounterDate,
    originalEncounterDateString,
    isPatientConnected,
    patientId,
    patientName,

    // Status indicators
    isEncounterUpdating,
    isDateUpdating,

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
    updateEncounterDate,

    // Voice recorder
    voiceRecorder,
  };

  return (
    <EncuentroContext.Provider value={value}>
      {children}
    </EncuentroContext.Provider>
  );
}

// Custom hook to use the context
export function useEncuentroContext() {
  const context = useContext(EncuentroContext);
  if (context === undefined) {
    throw new Error(
      "useEncuentroContext must be used within an EncuentroProvider"
    );
  }
  return context;
}
