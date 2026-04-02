import React from "react";
import { DocumentProvider } from "./DocumentContext";
import { ContentProvider } from "./ContentContext";
import { GenerationProvider } from "./GenerationContext";
import { TranscriptionProvider } from "./TranscriptionContext";
import { EncuentroProvider } from "./EncuentroContext";

type AppProvidersProps = {
  children: React.ReactNode;
  encounterId: number;
  initialTranscriptionDocId?: number | null;
};

/**
 * Encounter detail state is intentionally centralized here.
 * Keep long-lived side effects in these providers instead of recreating
 * feature-level hooks with their own SSE lifecycle or duplicate state.
 */
export function AppProviders({
  children,
  encounterId,
  initialTranscriptionDocId = null,
}: AppProvidersProps) {
  // Provider order is part of the contract because downstream providers depend
  // on state created by the earlier ones.
  return (
    <EncuentroProvider
      encounterId={encounterId}
      transcriptionDocId={initialTranscriptionDocId ?? undefined}
    >
      <DocumentProvider encounterId={encounterId}>
        <ContentProvider>
          <TranscriptionProvider
            initialTranscriptionDocId={initialTranscriptionDocId}
            encounterId={encounterId}
          >
            <GenerationProvider encounterId={encounterId}>
              {children}
            </GenerationProvider>
          </TranscriptionProvider>
        </ContentProvider>
      </DocumentProvider>
    </EncuentroProvider>
  );
}
