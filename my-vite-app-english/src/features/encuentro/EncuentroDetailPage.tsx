import { useRef, useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import EncuentroHeader from "../encuentroHeader/EncuentroHeader";
import DocumentArea from "../encuentroTextArea/DocumentArea";

export default function EncuentroDetailPage() {
  // Get the id parameter from the URL
  const { id } = useParams<{ id: string }>();

  // All hooks must be at the top level, before any conditionals
  const [encounterName, setEncounterName] = useState("Consulta médica");
  const [encounterDate] = useState("Sin fecha");
  const [isPatientConnected, setIsPatientConnected] = useState(false);
  const [patientId, setPatientId] = useState<number | null>(null);
  const [patientName, setPatientName] = useState("");
  const [transcriptionDocId, setTranscriptionDocId] = useState<
    number | undefined
  >(undefined);
  const [isUpdating] = useState(false);
  const generateDocumentationRef = useRef<(() => void) | null>(null);
  const [transcriptionCompleteTimestamp, setTranscriptionCompleteTimestamp] =
    useState<number | null>(null);

  // All useCallback hooks must also be at top level
  const handleTranscriptionComplete = useCallback(() => {
    console.log(
      `[ENCOUNTER] Transcription complete callback triggered. Current transcriptionDocId: ${transcriptionDocId}`
    );
    setTranscriptionCompleteTimestamp(Date.now());
  }, [transcriptionDocId]);

  const handleGenerateDocumentation = useCallback(() => {
    if (generateDocumentationRef.current) {
      generateDocumentationRef.current();
    }
  }, []);

  const handleTranscriptionDocumentFound = useCallback((docId: number) => {
    setTranscriptionDocId(docId);
  }, []);

  const registerGenerateDocumentationHandler = useCallback(
    (handler: () => void) => {
      generateDocumentationRef.current = handler;
    },
    []
  );

  const handleUpdatePatient = useCallback(
    (patientId: number, patientName: string) => {
      setPatientId(patientId);
      setPatientName(patientName);
      setIsPatientConnected(true);
    },
    []
  );

  const handleUpdatePatientAndEncounter = useCallback(
    (patientId: number, patientName: string, encounterName: string) => {
      setPatientId(patientId);
      setPatientName(patientName);
      setEncounterName(encounterName);
      setIsPatientConnected(true);
    },
    []
  );

  // useEffect needs to be used at the top level as well, but can have conditional logic inside
  useEffect(() => {
    if (!id) return; // Safe to have conditions inside hooks

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
  }, [id]); // Use id instead of encounterId since encounterId is defined after conditions

  // Now we can have conditional logic
  if (!id) {
    return <div>Encounter ID not found</div>;
  }

  // Convert id to number for API calls
  const encounterId = parseInt(id, 10);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
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
        onTranscriptionComplete={handleTranscriptionComplete}
      />
      <div className="flex-1 overflow-hidden">
        <DocumentArea
          encounterId={encounterId}
          onTranscriptionDocumentFound={handleTranscriptionDocumentFound}
          registerGenerateDocumentationHandler={
            registerGenerateDocumentationHandler
          }
          transcriptionCompleteTimestamp={transcriptionCompleteTimestamp}
          transcriptionDocId={transcriptionDocId}
        />
      </div>
    </div>
  );
}
