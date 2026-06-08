import {
  openIndexedDb,
  withIndexedDbStore,
} from "@/lib/indexedDbStore";

export type LocalSectionStatus =
  | "recorded"
  | "discarded_no_voice"
  | "upload_url_pending"
  | "uploading"
  | "uploaded"
  | "registering"
  | "registered"
  | "failed_retryable"
  | "failed_final";

export type LocalAudioSection = {
  local_section_id: string;
  recording_session_id: string;
  encounter_id: number;
  document_id: number;
  section_index: number;
  start_time_ms: number;
  end_time_ms: number;
  overlap_ms: number;
  original_blob?: Blob;
  clipped_blob?: Blob;
  original_content_type: string;
  clipped_content_type: string;
  status: LocalSectionStatus;
  retry_count: number;
  speech_frame_count?: number;
  discard_reason?: string;
  original_gcs_object_name?: string;
  clipped_gcs_object_name?: string;
  transcription_source_gcs_object_name?: string;
  frontend_vad_metadata?: Record<string, unknown>;
  backend_section_id?: string;
  created_at: string;
  updated_at: string;
};

const DB_NAME = "vexthealth-audio-sections";
const DB_VERSION = 2;
const STORE_NAME = "sections";
const databaseDefinition = {
  name: DB_NAME,
  version: DB_VERSION,
  stores: {
    [STORE_NAME]: {
      keyPath: "local_section_id",
      indexes: [
        { name: "encounter_id", keyPath: "encounter_id" },
        { name: "recording_session_id", keyPath: "recording_session_id" },
        { name: "status", keyPath: "status" },
      ],
    },
    debug_sections: {
      keyPath: "id",
      indexes: [
        { name: "status", keyPath: "status" },
        { name: "createdAt", keyPath: "createdAt" },
      ],
    },
  },
} as const;

export async function saveLocalSection(section: LocalAudioSection) {
  await withIndexedDbStore(databaseDefinition, STORE_NAME, "readwrite", (store) =>
    store.put(section),
  );
}

export async function updateLocalSection(
  localSectionId: string,
  updates: Partial<LocalAudioSection>,
) {
  const current = await getLocalSection(localSectionId);
  if (!current) return;
  await saveLocalSection({
    ...current,
    ...updates,
    updated_at: new Date().toISOString(),
  });
}

export async function getLocalSection(
  localSectionId: string,
): Promise<LocalAudioSection | undefined> {
  return withIndexedDbStore<LocalAudioSection>(databaseDefinition, STORE_NAME, "readonly", (store) =>
    store.get(localSectionId),
  );
}

export async function listPendingSections(
  encounterId?: number,
): Promise<LocalAudioSection[]> {
  const db = await openIndexedDb(databaseDefinition);
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.getAll();
    request.onsuccess = () => {
      const sections = (request.result as LocalAudioSection[])
        .filter(
          (section) =>
            section.status !== "registered" &&
            section.status !== "discarded_no_voice",
        )
        .filter((section) =>
          encounterId ? section.encounter_id === encounterId : true,
        )
        .sort((a, b) => a.section_index - b.section_index);
      resolve(sections);
    };
    request.onerror = () => reject(request.error);
  });
}

export async function deleteLocalSectionBlob(localSectionId: string) {
  const current = await getLocalSection(localSectionId);
  if (!current) return;
  const withoutBlob: Omit<LocalAudioSection, "original_blob" | "clipped_blob"> = {
    local_section_id: current.local_section_id,
    recording_session_id: current.recording_session_id,
    encounter_id: current.encounter_id,
    document_id: current.document_id,
    section_index: current.section_index,
    start_time_ms: current.start_time_ms,
    end_time_ms: current.end_time_ms,
    overlap_ms: current.overlap_ms,
    original_content_type: current.original_content_type,
    clipped_content_type: current.clipped_content_type,
    status: current.status,
    retry_count: current.retry_count,
    speech_frame_count: current.speech_frame_count,
    discard_reason: current.discard_reason,
    original_gcs_object_name: current.original_gcs_object_name,
    clipped_gcs_object_name: current.clipped_gcs_object_name,
    transcription_source_gcs_object_name:
      current.transcription_source_gcs_object_name,
    frontend_vad_metadata: current.frontend_vad_metadata,
    backend_section_id: current.backend_section_id,
    created_at: current.created_at,
    updated_at: current.updated_at,
  };
  await saveLocalSection({
    ...withoutBlob,
    status: "registered",
    updated_at: new Date().toISOString(),
  });
}
