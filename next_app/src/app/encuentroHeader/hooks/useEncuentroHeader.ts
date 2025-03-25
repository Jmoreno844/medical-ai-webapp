import { useState, useEffect } from "react";
import { useVoiceRecorder } from "./audio/useVoiceRecorder";
import { useEncounter } from "../../encuentro/hooks/useEncounter";
import { useRouter } from "next/navigation";
import useEncuentroList from "../../app_layout/hooks/Encuentros/useEncuentroList";
// Import useEncuentroDetail
import { useEncuentroDetail } from "../../app_layout/hooks/Encuentros/useEncuentroDetail";

/**
 * Interface for the return value of useEncuentroHeader hook
 */
interface UseEncuentroHeaderReturn {
    // Modal state
    isModalOpen: boolean;
    isUnlinkModalOpen: boolean;
    isDeleteModalOpen: boolean;
    deleteErrorMessage: string | null;
    deleteSuccess: boolean;
    redirectInfo: { path: string; name: string } | null;
    redirectCountdown: number;
    progressPercentage: number;

    // Encounter data
    encounterIdFromUrl: number;
    encounterName: string;

    // Add these properties related to patient connection
    isPatientConnected: boolean;
    patientId: number | null;
    patientName: string;

    // Actions
    setIsModalOpen: (isOpen: boolean) => void;
    setIsUnlinkModalOpen: (isOpen: boolean) => void;
    setIsDeleteModalOpen: (isOpen: boolean) => void;
    handleEditClick: () => void;
    handleSelectPatient: (patientId: number, patientName: string) => void;
    handleCreatePatient: (patientName: string) => void;
    handleUpdatePatientAndEncounter: (
        patientId: number,
        patientName: string,
        encounterName: string
    ) => void;
    handleUnlinkClick: () => void;
    handleUnlinkConfirm: () => Promise<void>;
    handleDeleteClick: () => void;
    handleDeleteConfirm: () => Promise<void>;

    // Voice recorder integration
    voiceRecorder: ReturnType<typeof useVoiceRecorder>;

    // Encounter update status
    isEncounterUpdating: boolean;
}

/**
 * Custom hook to manage the EncuentroHeader functionality
 *
 * @param encounterIdFromUrl - ID of the current encounter
 * @param onUpdatePatient - Callback to update patient information
 * @param onUpdatePatientAndEncounter - Callback to update both patient and encounter information
 * @param transcriptionDocId - Optional ID of the transcription document
 * @returns Object containing state and functions for EncuentroHeader
 */
export function useEncuentroHeader(
    encounterIdFromUrl: number,
    onUpdatePatient: (
        patientId: number,
        patientName: string
    ) => void = () => {},
    onUpdatePatientAndEncounter: (
        patientId: number,
        patientName: string,
        encounterName: string
    ) => void = () => {},
    transcriptionDocId?: number
): UseEncuentroHeaderReturn {
    // State for modals
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [isUnlinkModalOpen, setIsUnlinkModalOpen] = useState(false);
    const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
    const [deleteErrorMessage, setDeleteErrorMessage] = useState<string | null>(
        null
    );

    // State for success feedback
    const [deleteSuccess, setDeleteSuccess] = useState(false);
    const [redirectInfo, setRedirectInfo] = useState<{
        path: string;
        name: string;
    } | null>(null);
    const [redirectCountdown, setRedirectCountdown] = useState(0.5);
    const [progressPercentage, setProgressPercentage] = useState(0);

    // Add state for encounter name
    const [encounterName, setEncounterName] = useState("Consulta médica");

    // Add state for patient data
    const [isPatientConnected, setIsPatientConnected] = useState(false);
    const [patientId, setPatientId] = useState<number | null>(null);
    const [patientName, setPatientName] = useState("");

    // Hook for encounter operations
    const {
        updateEncounter,
        deleteEncounter,
        isLoading: isEncounterUpdating,
    } = useEncounter(encounterIdFromUrl);

    // Use the useEncuentroDetail hook instead of direct fetch
    const { encuentro, loading: encounterDataLoading } =
        useEncuentroDetail(encounterIdFromUrl);

    // Update encounter name when data is available
    useEffect(() => {
        if (encuentro) {
            // Set encounter name
            if (encuentro.nombre_encuentro) {
                setEncounterName(encuentro.nombre_encuentro);
            }

            // Set patient connection state
            setIsPatientConnected(!!encuentro.paciente_conectado);

            // Set patient data if connected
            if (encuentro.paciente_conectado) {
                setPatientId(encuentro.id_paciente || null);
                setPatientName(encuentro.nombre_paciente || "");
            } else {
                setPatientId(null);
                setPatientName("");
            }
        }
    }, [encuentro]);

    // Hook for encounter list to get encounters for redirection
    const { encuentros } = useEncuentroList();

    // Router for navigation
    const router = useRouter();

    // Voice recorder integration
    const voiceRecorder = useVoiceRecorder(transcriptionDocId);

    /**
     * Effect for countdown and redirect after successful deletion
     */
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

            // Handle the progress bar animation
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
    const handleSelectPatient = async (
        patientId: number,
        patientName: string
    ) => {
        console.log(`Selected patient: ID=${patientId}, Name=${patientName}`);

        // Use updateEncounter to update the patient connection in the database
        // Also set the encounter name to match the patient name
        const success = await updateEncounter(encounterIdFromUrl, {
            id_paciente: patientId,
            paciente_conectado: true,
            nombre_encuentro: patientName, // Add this line to update encounter name
        });

        if (success) {
            // Update local state to reflect the new encounter name
            setEncounterName(patientName);

            // Call the callback function to update UI state
            onUpdatePatient(patientId, patientName);
        } else {
            console.error("Failed to update patient connection");
        }
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
    const handleUpdatePatientAndEncounter = async (
        patientId: number,
        patientName: string,
        encounterName: string
    ) => {
        console.log(
            `Updating both patient and encounter: PatientID=${patientId}, PatientName=${patientName}, EncounterName=${encounterName}`
        );

        // Use updateEncounter to update both the patient and encounter name in the database
        const success = await updateEncounter(encounterIdFromUrl, {
            id_paciente: patientId,
            paciente_conectado: true,
            nombre_encuentro: encounterName,
        });

        if (success) {
            // Update local encounter name state
            setEncounterName(encounterName);
            // Call the callback function to update UI state
            onUpdatePatientAndEncounter(patientId, patientName, encounterName);
        } else {
            console.error("Failed to update patient and encounter information");
        }
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
        const success = await updateEncounter(encounterIdFromUrl, {
            paciente_conectado: false,
            id_paciente: null,
            nombre_encuentro: "Encuentro Nuevo", // Reset encounter name
        });

        if (success) {
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

    return {
        // Modal state
        isModalOpen,
        isUnlinkModalOpen,
        isDeleteModalOpen,
        deleteErrorMessage,
        deleteSuccess,
        redirectInfo,
        redirectCountdown,
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

        // Voice recorder integration
        voiceRecorder,

        // Status
        isEncounterUpdating,

        // Current encounter data
        encounterIdFromUrl,
        encounterName, // Use state variable instead of encounter?.nombre_encuentro

        // Add these properties to the return object
        isPatientConnected,
        patientId,
        patientName,
    };
}
