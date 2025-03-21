"use client";
import React, { useState } from "react";
import EncuentroHeader from "../../encuentroHeader/EncuentroHeader";
import { DocumentArea } from "../../encuentroTextArea";
import { useEncuentroDetail } from "../../app_layout/hooks/Encuentros/useEncuentroDetail";
import { useEncounter } from "../hooks/useEncounter";
import { usePatients } from "../../encuentroHeader/hooks/usePatients";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorDisplay from "@/components/ErrorDisplay";
import { format } from "date-fns";
import { es } from "date-fns/locale";

/**
 * Props for the EncounterDetailClient component
 */
interface EncounterDetailClientProps {
    /** Encounter ID from URL params */
    id: string;
}

/**
 * Main client component for the encounter detail page
 *
 * Handles loading encounter data, patient management, and
 * UI state for the encounter detail view
 *
 * @param props - Component props
 * @returns React component
 */
export function EncounterDetailClient({ id }: EncounterDetailClientProps) {
    // Convert string ID to number
    const encounterId = parseInt(id);

    // State to store transcription document ID
    const [transcriptionDocId, setTranscriptionDocId] = useState<
        number | undefined
    >();

    // ========== HOOKS ==========
    // Fetch encounter data
    const { encuentro, loading, error, refetch } =
        useEncuentroDetail(encounterId);

    // Manage encounter updates
    const {
        updateEncounter,
        isLoading: isUpdatingEncounter,
        error: updateEncounterError,
    } = useEncounter(encounterId);

    // Manage patient updates
    const {
        updatePatient,
        isLoading: isUpdatingPatient,
        error: updatePatientError,
    } = usePatients();

    // Combined loading state
    const isUpdating = isUpdatingEncounter || isUpdatingPatient;

    // ========== UTILITY FUNCTIONS ==========
    /**
     * Format datetime to a readable format
     *
     * @param dateTimeStr - ISO date string
     * @returns Formatted date string
     */
    const formatDateTime = (dateTimeStr: string): string => {
        try {
            return format(new Date(dateTimeStr), "dd MMMM yyyy HH:mm", {
                locale: es,
            });
        } catch {
            return dateTimeStr;
        }
    };

    // ========== EVENT HANDLERS ==========
    /**
     * Handle updating patient information for an encounter
     *
     * @param patientId - ID of the patient to connect
     * @param patientName - Name to use for the patient/encounter
     */
    const handleUpdatePatient = async (
        patientId: number,
        patientName: string
    ) => {
        console.log(
            `Updating encounter ${encounterId} with patient ${patientId} (${patientName})`
        );

        try {
            // Create update payload
            const updateData = {
                id_paciente: patientId,
                nombre_encuentro: patientName,
                paciente_conectado: true, // Explicitly connect patient
            };

            console.log("Update data being sent:", updateData);

            // Update the encounter
            const success = await updateEncounter(encounterId, updateData);

            if (success) {
                // Refresh data
                await refetch();
            }
        } catch (err) {
            console.error("Error in handleUpdatePatient:", err);
        }
    };

    /**
     * Handle updating both patient name and encounter name
     *
     * @param patientId - ID of the patient to update
     * @param patientName - New name for the patient
     * @param encounterName - New name for the encounter
     */
    const handleUpdatePatientAndEncounter = async (
        patientId: number,
        patientName: string,
        encounterName: string
    ) => {
        try {
            console.log(
                `Updating patient ${patientId} name to "${patientName}"`
            );
            console.log(
                `Updating encounter ${encounterId} name to "${encounterName}"`
            );

            // First, update the patient's name
            const patientUpdateSuccess = await updatePatient(
                patientId,
                patientName
            );

            if (!patientUpdateSuccess) {
                return;
            }

            // Then, update the encounter name
            const updateData = {
                id_paciente: patientId,
                nombre_encuentro: encounterName,
                paciente_conectado: true,
            };

            const encounterUpdateSuccess = await updateEncounter(
                encounterId,
                updateData
            );

            if (encounterUpdateSuccess) {
                // Refresh the encounter data to see the changes
                await refetch();
            }
        } catch (err) {
            console.error("Error in handleUpdatePatientAndEncounter:", err);
        }
    };

    // Handler for receiving transcription document ID
    const handleTranscriptionDocFound = (docId: number) => {
        setTranscriptionDocId(docId);
    };

    if (loading) {
        return (
            <>
                <EncuentroHeader
                    encounterName="Cargando encuentro..."
                    encounterDate="Cargando fecha..."
                />
                <div className="flex justify-center items-center h-[calc(100vh-64px)]">
                    <LoadingSpinner />
                </div>
            </>
        );
    }

    if (error) {
        return (
            <>
                <EncuentroHeader
                    encounterName="Error al cargar"
                    encounterDate="--"
                />
                <ErrorDisplay
                    message="No se pudo cargar la información del encuentro"
                    details={error}
                />
            </>
        );
    }

    return (
        <>
            <EncuentroHeader
                encounterName={encuentro?.nombre_encuentro || "Consulta médica"}
                encounterDate={
                    encuentro?.fecha
                        ? formatDateTime(encuentro.fecha)
                        : "Sin fecha"
                }
                onUpdatePatient={handleUpdatePatient}
                onUpdatePatientAndEncounter={handleUpdatePatientAndEncounter}
                isUpdating={isUpdating}
                isPatientConnected={!!encuentro?.paciente_conectado}
                patientId={encuentro?.id_paciente || 0}
                patientName={encuentro?.nombre_paciente || ""}
                transcriptionDocId={transcriptionDocId}
            />
            <div className="p-4">
                <DocumentArea
                    encounterId={encounterId}
                    onTranscriptionDocumentFound={handleTranscriptionDocFound}
                />
            </div>
        </>
    );
}
