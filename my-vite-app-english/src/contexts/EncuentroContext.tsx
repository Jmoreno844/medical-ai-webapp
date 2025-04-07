import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { useNavigate } from "react-router-dom";
import { useVoiceRecorder } from "../features/encuentroHeader/hooks/audio/useVoiceRecorder";
import { useEncounter } from "../features/encuentro/hooks/useEncounter";
import useEncuentroList from "../features/app_layout/hooks/Encuentros/useEncuentroList";

// Define the Encuentro interface if it's not imported
export interface Encuentro {
  id: number;
  nombre_encuentro: string;
  fecha: string;
  id_paciente?: number;
  nombre_paciente?: string;
  paciente_conectado?: boolean;
  has_been_transcribed?: boolean;
  // Add other fields as needed
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
    console.error("Error formatting date:", error);
    return "Sin fecha";
  }
};

/**
 * EncuentroContext provides data and functionality for managing medical encounters
 */
type EncuentroContextType = {
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
  const voiceRecorder = useVoiceRecorder(transcriptionDocId);

  // Fetch data function
  const fetchData = useCallback(async () => {
    if (!encounterId) {
      setError("ID no válido");
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    console.log(`Fetching encounter data for ID: ${encounterId}`);

    try {
      const response = await axiosInstance.get(
        `/api/encuentros/${encounterId}`
      );
      console.log("Encounter data received:", response.data);
      setEncuentro(response.data);

      // Update local state with fetched data
      if (response.data) {
        const data = response.data;
        if (data.nombre_encuentro) {
          setEncounterName(data.nombre_encuentro);
        }

        if (data.fecha) {
          setEncounterDate(formatDate(data.fecha));
          setOriginalEncounterDateString(data.fecha);
        }

        setIsPatientConnected(!!data.paciente_conectado);

        if (data.paciente_conectado) {
          setPatientId(data.id_paciente || null);
          setPatientName(data.nombre_paciente || "");
        } else {
          setPatientId(null);
          setPatientName("");
        }
      }
    } catch (err: any) {
      const errorMsg =
        err.response?.data?.message || err.message || "Error desconocido";
      setError(errorMsg);
      console.error("Error fetching encounter:", errorMsg, err);
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
    let countdownTimer: number;
    let progressTimer: number;

    if (deleteSuccess && redirectInfo) {
      if (redirectCountdown > 0) {
        countdownTimer = setTimeout(() => {
          setRedirectCountdown(0);
        }, 500);
      } else {
        console.log(`Attempting navigation to: ${redirectInfo.path}`);
        try {
          navigate(redirectInfo.path, { replace: true });
          setTimeout(() => {
            if (
              window.location.pathname.includes(`/encuentro/${encounterId}`)
            ) {
              console.log(`Using fallback navigation to: ${redirectInfo.path}`);
              window.location.href = redirectInfo.path;
            }
          }, 200);
        } catch (err) {
          console.error("Navigation error:", err);
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
      if (countdownTimer) clearTimeout(countdownTimer);
      if (progressTimer) clearTimeout(progressTimer);
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
        console.log(
          `[ENCUENTRO] Updating encounter ${encounterId} with:`,
          data
        );
        const response = await axiosInstance.patch(
          `/api/encuentros/${encounterId}`,
          data
        );

        if (response.status === 200) {
          await fetchData();
          return true;
        }
        return false;
      } catch (error) {
        console.error(`[ENCUENTRO] Error updating encounter:`, error);
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
        console.log(`Updating encounter date to: ${isoDate}`);

        const response = await axiosInstance.patch(
          `/api/encuentros/${encounterId}`,
          {
            fecha: isoDate,
          }
        );

        if (response.status === 200) {
          setEncounterDate(formatDate(isoDate));
          setOriginalEncounterDateString(isoDate);
          console.log("Encounter date updated successfully");
          return true;
        } else {
          console.error("Failed to update encounter date:", response);
          return false;
        }
      } catch (error) {
        console.error("Error updating encounter date:", error);
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
      console.log(`Selected patient: ID=${patientId}, Name=${patientName}`);

      const success = await updateEncounter(encounterId, {
        id_paciente: patientId,
        paciente_conectado: true,
        nombre_encuentro: patientName,
      });

      if (success) {
        setEncounterName(patientName);
        setIsPatientConnected(true);
        setPatientId(patientId);
        setPatientName(patientName);
        setIsModalOpen(false);
      } else {
        console.error("Failed to update patient connection");
      }
    },
    [encounterId, updateEncounter]
  );

  /**
   * Handle patient creation from modal
   */
  const handleCreatePatient = useCallback((patientName: string) => {
    console.log(`New patient created: ${patientName}`);
    // The actual update is handled in handleSelectPatient which is called after creation
  }, []);

  /**
   * Handle updating both patient and encounter names
   */
  const handleUpdatePatientAndEncounter = useCallback(
    async (patientId: number, patientName: string, encounterName: string) => {
      console.log(
        `Updating both patient and encounter: PatientID=${patientId}, PatientName=${patientName}, EncounterName=${encounterName}`
      );

      const success = await updateEncounter(encounterId, {
        id_paciente: patientId,
        paciente_conectado: true,
        nombre_encuentro: encounterName,
      });

      if (success) {
        setEncounterName(encounterName);
        setIsPatientConnected(true);
        setPatientId(patientId);
        setPatientName(patientName);
      } else {
        console.error("Failed to update patient and encounter information");
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
      paciente_conectado: false,
      id_paciente: null,
      nombre_encuentro: "Encuentro Nuevo",
    });

    if (success) {
      console.log("Patient unlinked successfully");
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
      console.log("Encounter deleted successfully");
      setDeleteSuccess(true);
      setProgressPercentage(0);

      if (encuentros.length > 0) {
        const nextEncounter = encuentros.find((e) => e.id !== encounterId);

        if (nextEncounter) {
          setRedirectInfo({
            path: `/encuentro/${nextEncounter.id}`,
            name: nextEncounter.nombre_encuentro,
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
      console.error("Error deleting encounter:", result);
    }
  }, [deleteEncounter, encuentros, encounterId]);

  // Context value
  const value: EncuentroContextType = {
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
