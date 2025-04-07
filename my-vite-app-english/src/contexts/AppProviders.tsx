import React from "react";
import { DocumentProvider } from "./DocumentContext";
import { ContentProvider } from "./ContentContext";
import { GenerationProvider } from "./GenerationContext";
import { TranscriptionProvider } from "./TranscriptionContext";

type AppProvidersProps = {
  children: React.ReactNode;
  encounterId: number;
  initialTranscriptionDocId?: number | null;
};

/**
 * Combined providers component that wraps the application with all necessary contexts
 *
 * Ensures proper nesting order of contexts and dependency injection
 */
export function AppProviders({
  children,
  encounterId,
  initialTranscriptionDocId = null,
}: AppProvidersProps) {
  return (
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
  );
}
