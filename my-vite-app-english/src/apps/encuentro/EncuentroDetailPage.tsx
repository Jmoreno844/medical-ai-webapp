import { useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import EncuentroHeader from "../encuentroHeader/EncuentroHeader";
import DocumentArea from "../encuentroTextArea/DocumentArea";
import { AppProviders } from "@/contexts/AppProviders";

export default function EncuentroDetailPage() {
  // Get the encounter ID from URL params
  const { id } = useParams<{ id: string }>();
  const encounterId = id ? parseInt(id, 10) : 0;

  // We only need a minimal state at this level now
  const [transcriptionDocId, setTranscriptionDocId] = useState<number | null>(
    null //
  );

  // Handler for when a transcription document is found
  const handleTranscriptionDocumentFound = useCallback((docId: number) => {
    setTranscriptionDocId(docId);
  }, []);

  // Use the AppProviders to wrap everything
  return (
    <AppProviders
      encounterId={encounterId}
      initialTranscriptionDocId={transcriptionDocId}
    >
      <div className="flex flex-col h-screen overflow-hidden">
        <EncuentroHeader />
        <div className="flex-1 overflow-hidden">
          <DocumentArea
            onTranscriptionDocumentFound={handleTranscriptionDocumentFound}
          />
        </div>
      </div>
    </AppProviders>
  );
}
