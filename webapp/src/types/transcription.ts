export type TranscriptionSpeaker =
  | "MEDICO"
  | "PACIENTE"
  | "ACOMPANANTE"
  | "DESCONOCIDO";

export type TranscriptionTurn = {
  speaker: TranscriptionSpeaker;
  text: string;
  overlaps_previous: boolean;
  overlaps_next: boolean;
};

export type ChunkTranscript = {
  chunk_id: string;
  start_ms: number;
  end_ms: number;
  turns: TranscriptionTurn[];
};

const SPEAKER_LABELS: Record<TranscriptionSpeaker, string> = {
  MEDICO: "Médico",
  PACIENTE: "Paciente",
  ACOMPANANTE: "Acompañante",
  DESCONOCIDO: "Desconocido",
};

export function renderTurnsToClinicalText(turns: TranscriptionTurn[]): string {
  return turns
    .map((turn) => {
      const text = turn.text.trim();
      if (!text) {
        return "";
      }
      return `${SPEAKER_LABELS[turn.speaker]}: ${text}`;
    })
    .filter(Boolean)
    .join("\n\n");
}

export function mergeConsecutiveTurns(
  turns: TranscriptionTurn[],
): TranscriptionTurn[] {
  const merged: TranscriptionTurn[] = [];

  for (const turn of turns) {
    const current: TranscriptionTurn = {
      ...turn,
      text: turn.text.trim(),
    };
    if (!current.text) {
      continue;
    }

    const previous = merged.at(-1);
    const canMerge =
      previous !== undefined &&
      previous.speaker === current.speaker &&
      previous.overlaps_next === false &&
      current.overlaps_previous === false;

    if (canMerge) {
      previous.text = `${previous.text} ${current.text}`.trim();
      previous.overlaps_next = current.overlaps_next;
    } else {
      merged.push({ ...current });
    }
  }

  return merged;
}

export function renderTurnsToBlockText(turns: TranscriptionTurn[]): string {
  return turns
    .map((turn) => {
      const text = turn.text.trim();
      if (!text) {
        return "";
      }
      return `${SPEAKER_LABELS[turn.speaker]}: ${text}`;
    })
    .filter(Boolean)
    .join("\n");
}
