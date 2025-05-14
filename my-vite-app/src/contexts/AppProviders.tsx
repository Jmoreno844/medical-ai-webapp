import React from "react";
import { DocumentProvider } from "./DocumentContext";
import { ContentProvider } from "./ContentContext";
import { GenerationProvider } from "./GenerationContext";
import { TranscriptionProvider } from "./TranscriptionContext";
import { EncuentroProvider } from "./EncuentroContext"; // Add this

type AppProvidersProps = {
  children: React.ReactNode;
  encounterId: number;
  initialTranscriptionDocId?: number | null;
};

/**
 * Combined providers component that wraps the application with all necessary contexts
 *
 * Ensures proper nesting order of contexts and dependency injection:
 * 1. DocumentProvider (base document management)
 * 2. ContentProvider (depends on DocumentContext)
 * 3. TranscriptionProvider (depends on ContentContext for updates)
 * 4. GenerationProvider (depends on other contexts)
 */
export function AppProviders({
  children,
  encounterId,
  initialTranscriptionDocId = null,
}: AppProvidersProps) {
  // The order is important for dependency resolution
  return (
    <EncuentroProvider encounterId={encounterId}>
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
