import {
  openIndexedDb,
  withIndexedDbStore,
} from "@/lib/indexedDbStore";
import type { RemovableSilence, SpeechInterval } from "@/audio/segmentation/types";

export type DebugCutReason =
  | "natural_pause"
  | "forced_maximum"
  | "manual_stop"
  | "silence_after_minimum"
  | "closing_soon_silence"
  | "wall_clock_limit"
  | "fallback"
  | "uploaded_audio";

export type DebugCutMetadata = {
  sectionDurationMs: number;
  speechDurationMs: number;
  speechFrameCount: number;
  hasDetectedSpeech: boolean;
  cutReason: DebugCutReason;
  overlapMs: number;
  speechIntervals: SpeechInterval[];
  removableSilences: RemovableSilence[];
  retainedIntervals: SpeechInterval[];
};

export type DebugWorkerCutMetadata = {
  originalDurationMs: number;
  retainedDurationMs: number;
  speechDurationMs: number;
  speechRatio: number;
  retainedIntervals: SpeechInterval[];
  removableSilences: RemovableSilence[];
  speechIntervals: SpeechInterval[];
  trimApplied: boolean;
};

export type DebugWorkerInputMetadata = {
  inputByteSize: number;
  decodedSampleCount: number;
  decodedDurationMs: number;
  sampleRateHz: number;
  trimmedAudioByteSize: number;
};

export type DebugCutComparison = {
  originalDurationMs: number;
  frontendRetainedDurationMs: number;
  workerRetainedDurationMs: number;
  retainedDurationDeltaMs: number;
  frontendRemovedSilenceMs: number;
  workerRemovedSilenceMs: number;
  silenceRemovedDeltaMs: number;
};

export type DebugTranscriptResult = {
  mode?: "transcribe" | "vad_only";
  provider: string;
  model: string;
  transcript: string;
  contentType: string;
  responseTimeMs: number;
  vadDecision: string;
  vadSpeechMs: number;
  vadSpeechRatio: number;
  vadErrorCode?: string | null;
  frontendCut: DebugCutMetadata;
  workerInput: DebugWorkerInputMetadata;
  workerCut: DebugWorkerCutMetadata;
  comparison: DebugCutComparison;
};

export type DebugSectionRecord = {
  id: string;
  blob: Blob;
  startMs: number;
  endMs: number;
  durationMs: number;
  blobDurationMs?: number;
  mimeType: string;
  frontendCut: DebugCutMetadata;
  transcripts: Partial<
    Record<"gemini" | "workerVad", DebugTranscriptResult>
  >;
  status: "recorded" | "processing" | "processed" | "failed";
  createdAt: string;
  updatedAt: string;
};

const DB_NAME = "vexthealth-audio-sections";
const DB_VERSION = 2;
const STORE_NAME = "debug_sections";

const databaseDefinition = {
  name: DB_NAME,
  version: DB_VERSION,
  stores: {
    sections: {
      keyPath: "local_section_id",
      indexes: [
        { name: "encounter_id", keyPath: "encounter_id" },
        { name: "recording_session_id", keyPath: "recording_session_id" },
        { name: "status", keyPath: "status" },
      ],
    },
    [STORE_NAME]: {
      keyPath: "id",
      indexes: [
        { name: "status", keyPath: "status" },
        { name: "createdAt", keyPath: "createdAt" },
      ],
    },
  },
} as const;

export async function listDebugSections(): Promise<DebugSectionRecord[]> {
  const db = await openIndexedDb(databaseDefinition);
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.getAll();
    request.onsuccess = () => {
      const items = (request.result as DebugSectionRecord[]).sort((a, b) =>
        a.startMs - b.startMs,
      );
      resolve(items);
    };
    request.onerror = () => reject(request.error);
  });
}

export async function saveDebugSection(section: DebugSectionRecord): Promise<void> {
  await withIndexedDbStore(databaseDefinition, STORE_NAME, "readwrite", (store) =>
    store.put(section),
  );
}

export async function updateDebugSection(
  sectionId: string,
  updates: Partial<DebugSectionRecord>,
): Promise<void> {
  const current = await getDebugSection(sectionId);
  if (!current) {
    return;
  }

  await saveDebugSection({
    ...current,
    ...updates,
    updatedAt: new Date().toISOString(),
  });
}

export async function getDebugSection(
  sectionId: string,
): Promise<DebugSectionRecord | undefined> {
  return withIndexedDbStore<DebugSectionRecord>(
    databaseDefinition,
    STORE_NAME,
    "readonly",
    (store) => store.get(sectionId),
  );
}

export async function clearDebugSections(): Promise<void> {
  await withIndexedDbStore(databaseDefinition, STORE_NAME, "readwrite", (store) =>
    store.clear(),
  );
}
