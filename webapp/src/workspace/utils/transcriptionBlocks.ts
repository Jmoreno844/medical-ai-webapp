import { RecordingSessionSection } from "@/features/encuentroHeader/hooks/audio/uploadService";
import {
  ChunkTranscript,
  renderTurnsToBlockText,
  TranscriptionTurn,
} from "@/types/transcription";
import { TranscriptionBlock } from "@/workspace/types";

export function formatTranscriptionTimestamp(startTimeMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(startTimeMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return [hours, minutes, seconds]
      .map((value) => String(value).padStart(2, "0"))
      .join(":");
  }

  return [minutes, seconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

function sectionTurns(section: RecordingSessionSection): TranscriptionTurn[] {
  if (section.turns?.length) {
    return section.turns;
  }
  const legacyText = String(section.raw_transcript ?? "").trim();
  if (!legacyText) {
    return [];
  }
  return [{ speaker: "DESCONOCIDO", text: legacyText, overlaps_previous: false, overlaps_next: false }];
}

export function buildTranscriptionBlocksFromChunks(
  chunks: ChunkTranscript[] | null | undefined,
): TranscriptionBlock[] {
  if (!chunks?.length) {
    return [];
  }

  return chunks
    .map((chunk) => ({
      sectionId: chunk.chunk_id,
      startTimeMs: chunk.start_ms,
      endTimeMs: chunk.end_ms,
      turns: chunk.turns,
      text: renderTurnsToBlockText(chunk.turns),
      status: "transcribed",
    }))
    .filter((block) => block.turns.length > 0);
}

export function buildTranscriptionBlocks(
  sections: RecordingSessionSection[] | null | undefined,
  chunks?: ChunkTranscript[] | null,
): TranscriptionBlock[] {
  if (chunks?.length) {
    return buildTranscriptionBlocksFromChunks(chunks);
  }

  if (!sections?.length) {
    return [];
  }

  return [...sections]
    .sort((left, right) => left.section_index - right.section_index)
    .map((section) => {
      const turns = sectionTurns(section);
      return {
        sectionId: section.section_id,
        startTimeMs: section.start_time_ms,
        endTimeMs: section.end_time_ms,
        turns,
        text: renderTurnsToBlockText(turns),
        status: section.status,
      };
    })
    .filter((block) => block.turns.length > 0);
}
