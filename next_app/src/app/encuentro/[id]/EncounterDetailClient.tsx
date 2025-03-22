"use client";

import React, { useRef, useState, useEffect, useCallback } from "react";
import EncuentroHeader from "../../encuentroHeader/EncuentroHeader";
import DocumentArea from "../../encuentroTextArea/DocumentArea";
// Import other necessary components

interface EncounterDetailClientProps {
    id: string;
}

export const EncounterDetailClient: React.FC<EncounterDetailClientProps> = ({
    id,
}) => {
    // Convert id to number if needed for API calls
    const encounterId = parseInt(id, 10);

    // State for the encounter and patient data
    const [encounterName, setEncounterName] = useState("Consulta médica");
    const [encounterDate, setEncounterDate] = useState("Sin fecha");
    const [isPatientConnected, setIsPatientConnected] = useState(false);
    const [patientId, setPatientId] = useState<number | null>(null);
    const [patientName, setPatientName] = useState("");
    const [transcriptionDocId, setTranscriptionDocId] = useState<
        number | undefined
    >(undefined);
    const [isUpdating, setIsUpdating] = useState(false);

    // Reference to store the document generation function
    const generateDocumentationRef = useRef<(() => void) | null>(null);

    // Handle document generation button click
    const handleGenerateDocumentation = useCallback(() => {
        if (generateDocumentationRef.current) {
            generateDocumentationRef.current();
        }
    }, []);

    // Handle when transcription document is found
    const handleTranscriptionDocumentFound = useCallback((docId: number) => {
        setTranscriptionDocId(docId);
    }, []);

    // Register the document generation handler from DocumentArea
    const registerGenerateDocumentationHandler = useCallback(
        (handler: () => void) => {
            generateDocumentationRef.current = handler;
        },
        []
    );

    // Update patient info handler
    const handleUpdatePatient = useCallback(
        (patientId: number, patientName: string) => {
            setPatientId(patientId);
            setPatientName(patientName);
            setIsPatientConnected(true);
            // Make API call to update patient association if needed
        },
        []
    );

    // Update both patient and encounter info handler
    const handleUpdatePatientAndEncounter = useCallback(
        (patientId: number, patientName: string, encounterName: string) => {
            setPatientId(patientId);
            setPatientName(patientName);
            setEncounterName(encounterName);
            setIsPatientConnected(true);
            // Make API call to update both if needed
        },
        []
    );

    // Fetch encounter data on component mount
    useEffect(() => {
        const fetchEncounterData = async () => {
            try {
                // Fetch encounter data from API
                // This would be your actual API call
                // const data = await fetchEncounterById(encounterId);
                // setEncounterName(data.name);
                // setEncounterDate(data.formattedDate);
                // setIsPatientConnected(!!data.patientId);
                // setPatientId(data.patientId);
                // setPatientName(data.patientName);
            } catch (error) {
                console.error("Failed to fetch encounter data:", error);
            }
        };

        fetchEncounterData();
    }, [encounterId]);

    return (
        <div className="flex flex-col h-screen">
            <EncuentroHeader
                encounterName={encounterName}
                encounterDate={encounterDate}
                onUpdatePatient={handleUpdatePatient}
                onUpdatePatientAndEncounter={handleUpdatePatientAndEncounter}
                isUpdating={isUpdating}
                isPatientConnected={isPatientConnected}
                patientId={patientId}
                patientName={patientName}
                transcriptionDocId={transcriptionDocId}
                onGenerateDocumentation={handleGenerateDocumentation}
            />
            <div className="flex-1 overflow-hidden">
                <DocumentArea
                    encounterId={encounterId}
                    onTranscriptionDocumentFound={
                        handleTranscriptionDocumentFound
                    }
                    registerGenerateDocumentationHandler={
                        registerGenerateDocumentationHandler
                    }
                />
            </div>
        </div>
    );
};
