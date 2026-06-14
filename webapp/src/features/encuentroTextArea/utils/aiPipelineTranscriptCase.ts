import type { TranscriptionBlock } from "@/workspace/types";

export type AiPipelineTranscriptTurn = {
  turn_id: number;
  speaker: string;
  text: string;
};

export type AiPipelineTranscriptChunk = {
  chunk_id: string;
  turns: AiPipelineTranscriptTurn[];
};

export type AiPipelineTranscriptCase = {
  session_id: string;
  language: string;
  chunks: AiPipelineTranscriptChunk[];
};

export function buildAiPipelineCaseFromBlocks(
  blocks: TranscriptionBlock[],
  sessionId: string,
): AiPipelineTranscriptCase | null {
  const chunks: AiPipelineTranscriptChunk[] = [];
  let turnId = 0;

  for (const block of blocks) {
    const turns: AiPipelineTranscriptTurn[] = [];
    for (const turn of block.turns) {
      const text = turn.text.trim();
      if (!text) {
        continue;
      }
      turns.push({
        turn_id: turnId,
        speaker: turn.speaker,
        text,
      });
      turnId += 1;
    }
    if (turns.length === 0) {
      continue;
    }
    chunks.push({
      chunk_id: block.sectionId || `s${chunks.length}`,
      turns,
    });
  }

  if (chunks.length === 0) {
    return null;
  }

  return {
    session_id: sessionId,
    language: "es",
    chunks,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function extractTranscriptCasePayload(
  payload: unknown,
): Record<string, unknown> {
  if (!isRecord(payload)) {
    throw new Error("El JSON debe ser un objeto.");
  }
  if (Array.isArray(payload.chunks)) {
    return payload;
  }
  if (isRecord(payload.transcript_json) && Array.isArray(payload.transcript_json.chunks)) {
    return payload.transcript_json;
  }
  throw new Error(
    "Formato no reconocido. Usa un case de ai-pipeline con chunks[] o transcript_json.chunks[].",
  );
}

export function parseAiPipelineTranscriptCaseFile(
  payload: unknown,
): AiPipelineTranscriptCase {
  const transcriptPayload = extractTranscriptCasePayload(payload);
  const rawChunks = transcriptPayload.chunks;
  if (!Array.isArray(rawChunks) || rawChunks.length === 0) {
    throw new Error("El case debe incluir al menos un chunk con turnos.");
  }

  const sessionId =
    typeof transcriptPayload.session_id === "string" &&
    transcriptPayload.session_id.trim()
      ? transcriptPayload.session_id.trim()
      : "imported_case";

  const chunks: AiPipelineTranscriptChunk[] = [];
  let inferredTurnId = 0;

  rawChunks.forEach((rawChunk, chunkIndex) => {
    if (!isRecord(rawChunk)) {
      throw new Error(`Chunk ${chunkIndex + 1} inválido.`);
    }
    const rawTurns = rawChunk.turns;
    if (!Array.isArray(rawTurns)) {
      throw new Error(`Chunk ${chunkIndex + 1} no tiene turns[].`);
    }

    const turns: AiPipelineTranscriptTurn[] = [];
    rawTurns.forEach((rawTurn, turnIndex) => {
      if (!isRecord(rawTurn)) {
        throw new Error(`Turno ${turnIndex + 1} del chunk ${chunkIndex + 1} inválido.`);
      }
      const speaker = rawTurn.speaker;
      const text = rawTurn.text;
      if (typeof speaker !== "string" || typeof text !== "string" || !text.trim()) {
        throw new Error(
          `Turno ${turnIndex + 1} del chunk ${chunkIndex + 1} requiere speaker y text.`,
        );
      }
      const storedTurnId = rawTurn.turn_id;
      const turnId =
        typeof storedTurnId === "number" && Number.isInteger(storedTurnId)
          ? storedTurnId
          : inferredTurnId;
      inferredTurnId = Math.max(inferredTurnId, turnId + 1);
      turns.push({
        turn_id: turnId,
        speaker,
        text: text.trim(),
      });
    });

    if (turns.length === 0) {
      return;
    }

    const chunkId =
      typeof rawChunk.chunk_id === "string" && rawChunk.chunk_id.trim()
        ? rawChunk.chunk_id.trim()
        : `s${chunks.length}`;

    chunks.push({
      chunk_id: chunkId,
      turns,
    });
  });

  if (chunks.length === 0) {
    throw new Error("El case no contiene turnos con texto.");
  }

  return {
    session_id: sessionId,
    language:
      typeof transcriptPayload.language === "string"
        ? transcriptPayload.language
        : "es",
    chunks,
  };
}
