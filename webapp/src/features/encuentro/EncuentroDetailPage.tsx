import { useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import EncuentroHeader from "../encuentroHeader/EncuentroHeader";
import DocumentArea from "../encuentroTextArea/DocumentArea";
import { AppProviders } from "@/contexts/AppProviders";
import CopilotSidePanel from "@/features/copilotDebug/CopilotSidePanel";

export default function EncuentroDetailPage() {
  // Get the encounter ID from URL params
  const { id } = useParams<{ id: string }>();
  const encounterId = id ? parseInt(id, 10) : 0;

  // We only need a minimal state at this level now
  const [transcriptionDocId, setTranscriptionDocId] = useState<number | null>(
    null
  );

  // Handler for when a transcription document is found
  const handleTranscriptionDocumentFound = useCallback((docId: number) => {
    setTranscriptionDocId(docId);
  }, []);
  const showCopilotDebugPanel =
    import.meta.env.DEV ||
    import.meta.env.VITE_ENABLE_COPILOT_DEBUG_PANEL === "true";

  // Use the AppProviders to wrap everything
  return (
    <AppProviders
      encounterId={encounterId}
      initialTranscriptionDocId={transcriptionDocId}
    >
      <div className="flex flex-col h-screen overflow-hidden">
        <EncuentroHeader />
        <div className="flex-1 overflow-hidden p-4">
          <div className="flex h-full flex-col gap-4 lg:flex-row">
            <div className="min-h-0 min-w-0 flex-1">
              <DocumentArea
                onTranscriptionDocumentFound={handleTranscriptionDocumentFound}
              />
            </div>
            {showCopilotDebugPanel && (
              <aside className="min-h-0 w-full shrink-0 overflow-y-auto lg:w-[380px] xl:w-[420px]">
                <CopilotSidePanel encounterId={encounterId} />
              </aside>
            )}
          </div>
        </div>
      </div>
    </AppProviders>
  );
}
