import allCasesJson from "../../../../evals/document_generation/cases.json";

type DocumentGenerationTranscription = {
  language?: string;
  sections: Array<{
    section_index: number;
    start_time_ms: number;
    end_time_ms: number;
    turns: Array<{
      speaker: string;
      text: string;
    }>;
  }>;
};

type DocumentGenerationCase = {
  id: string;
  context: string;
  notes?: string;
  transcription: DocumentGenerationTranscription;
};

export type DebugExtractionCase = {
  index: number;
  id: string;
  context: string;
  notes?: string;
  transcriptJson: Record<string, unknown>;
  language: string;
  patientName: string;
};

function transcriptionToTranscriptJson(
  caseId: string,
  transcription: DocumentGenerationTranscription,
): Record<string, unknown> {
  return {
    session_id: caseId,
    language: transcription.language ?? "es",
    chunks: transcription.sections.map((section) => ({
      chunk_id: String(section.section_index),
      start_ms: section.start_time_ms,
      end_ms: section.end_time_ms,
      turns: section.turns.map((turn) => ({
        speaker: turn.speaker,
        text: turn.text,
      })),
    })),
  };
}

const allCases = allCasesJson as DocumentGenerationCase[];

export const DEBUG_EXTRACTION_CASES: DebugExtractionCase[] = allCases.map(
  (caseItem, caseIndex) => ({
    index: caseIndex + 1,
    id: caseItem.id,
    context: caseItem.context,
    notes: caseItem.notes,
    transcriptJson: transcriptionToTranscriptJson(
      caseItem.id,
      caseItem.transcription,
    ),
    language: caseItem.transcription.language ?? "es",
    patientName: caseItem.id,
  }),
);

export const DEFAULT_DEBUG_EXTRACTION_CASE =
  DEBUG_EXTRACTION_CASES[DEBUG_EXTRACTION_CASES.length - 1] ??
  DEBUG_EXTRACTION_CASES[0];
