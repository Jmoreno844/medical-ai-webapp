import { RecordingSessionSection } from "@/features/encuentroHeader/hooks/audio/uploadService";
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

export function buildTranscriptionBlocks(
  sections: RecordingSessionSection[] | null | undefined,
): TranscriptionBlock[] {
  if (!sections?.length) {
    return [];
  }

  return [...sections]
    .sort((left, right) => left.section_index - right.section_index)
    .map((section) => ({
      sectionId: section.section_id,
      startTimeMs: section.start_time_ms,
      endTimeMs: section.end_time_ms,
      text: String(section.raw_transcript ?? "").trim(),
      status: section.status,
    }))
    .filter((block) => block.text.length > 0);
}
