import { type ChangeEvent, useRef, useState } from "react";
import { Copy, FileJson, Loader2, Upload } from "lucide-react";
import { Button } from "@/commons/components/ui/button";
import { useContentContext } from "@/contexts/ContentContext";
import { useDocumentDerivedStore } from "@/workspace/stores/documentDerivedStore";
import { buildTranscriptionBlocksFromChunks } from "@/workspace/utils/transcriptionBlocks";
import { renderTurnsToClinicalText } from "@/types/transcription";
import type { ChunkTranscript, TranscriptionTurn } from "@/types/transcription";
import { importTranscriptCaseForDocument } from "@/features/encuentroHeader/hooks/audio/uploadService";
import {
  buildAiPipelineCaseFromBlocks,
  parseAiPipelineTranscriptCaseFile,
} from "../utils/aiPipelineTranscriptCase";
import { logger } from "@/lib/logger";

type TranscriptionDevToolsProps = {
  documentId: number;
  encounterId: number;
  sessionId?: string | null;
};

export default function TranscriptionDevTools({
  documentId,
  encounterId,
  sessionId,
}: TranscriptionDevToolsProps) {
  const { reloadContent } = useContentContext();
  const completeTranscription = useDocumentDerivedStore(
    (state) => state.completeTranscription,
  );
  const transcriptionBlocks =
    useDocumentDerivedStore(
      (state) => state.derivedByDocumentId[String(documentId)]?.transcriptionBlocks,
    ) ?? [];

  const [error, setError] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  const [isImporting, setIsImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const exportSessionId =
    sessionId?.trim() ||
    `encounter-${encounterId}`;

  const buildExportJson = () => {
    const transcriptCase = buildAiPipelineCaseFromBlocks(
      transcriptionBlocks,
      exportSessionId,
    );
    if (!transcriptCase) {
      throw new Error("No hay turnos de transcripción para exportar.");
    }
    return JSON.stringify(transcriptCase, null, 2);
  };

  const handleCopyJson = async () => {
    setError(null);
    setCopyState("idle");
    try {
      await navigator.clipboard.writeText(buildExportJson());
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2000);
    } catch (copyError) {
      logger.error("[TranscriptionDevTools] copy failed", copyError);
      setCopyState("error");
      setError("No se pudo copiar el JSON al portapapeles.");
    }
  };

  const handleImportFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }

    setError(null);
    setIsImporting(true);
    try {
      const fileText = await file.text();
      const parsed = JSON.parse(fileText) as unknown;
      const transcriptCase = parseAiPipelineTranscriptCaseFile(parsed);
      const response = await importTranscriptCaseForDocument(
        documentId,
        transcriptCase,
      );
      if (!response?.success) {
        throw new Error(response?.error ?? "No se pudo importar el case.");
      }

      const chunks = (response.chunks ?? []) as ChunkTranscript[];
      const turns = chunks.flatMap((chunk) => chunk.turns as TranscriptionTurn[]);
      const renderedText =
        response.rendered_text?.trim() ||
        renderTurnsToClinicalText(turns);
      const blocks = buildTranscriptionBlocksFromChunks(chunks);
      completeTranscription(String(documentId), renderedText, blocks);
      await reloadContent(true);
    } catch (importError) {
      logger.error("[TranscriptionDevTools] import failed", importError);
      setError(
        importError instanceof Error
          ? importError.message
          : "No se pudo importar el case de transcripción.",
      );
    } finally {
      setIsImporting(false);
    }
  };

  const canCopy = transcriptionBlocks.length > 0;

  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-medium text-amber-950">
            Herramientas locales (ai-pipeline)
          </p>
          <p className="text-xs text-amber-800">
            Copia o importa un case JSON compatible con{" "}
            <code className="rounded bg-amber-100 px-1">ai-pipeline/cases/transcripts/</code>.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!canCopy}
            onClick={() => void handleCopyJson()}
          >
            <Copy className="mr-2 h-4 w-4" />
            {copyState === "copied"
              ? "Copiado"
              : copyState === "error"
                ? "Error al copiar"
                : "Copiar JSON"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isImporting}
            onClick={() => fileInputRef.current?.click()}
          >
            {isImporting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-2 h-4 w-4" />
            )}
            Subir case JSON
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => void handleImportFile(event)}
          />
        </div>
      </div>
      {error ? (
        <div className="mt-2 flex items-start gap-2 text-sm text-rose-700">
          <FileJson className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}
    </div>
  );
}
