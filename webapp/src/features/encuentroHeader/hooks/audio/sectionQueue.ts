export type LocalSectionStatus =
  | "recorded"
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
  blob?: Blob;
  content_type: string;
  status: LocalSectionStatus;
  retry_count: number;
  gcs_object_name?: string;
  backend_section_id?: string;
  created_at: string;
  updated_at: string;
};

const DB_NAME = "vexthealth-audio-sections";
const DB_VERSION = 1;
const STORE_NAME = "sections";

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;

  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, {
          keyPath: "local_section_id",
        });
        store.createIndex("encounter_id", "encounter_id");
        store.createIndex("recording_session_id", "recording_session_id");
        store.createIndex("status", "status");
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

  return dbPromise;
}

async function withStore<T>(
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => IDBRequest<T> | void
): Promise<T | undefined> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, mode);
    const store = transaction.objectStore(STORE_NAME);
    const request = fn(store);
    let result: T | undefined;

    if (request) {
      request.onsuccess = () => {
        result = request.result;
      };
      request.onerror = () => reject(request.error);
    }
    transaction.oncomplete = () => resolve(result);
    transaction.onerror = () => reject(transaction.error);
  });
}

export async function saveLocalSection(section: LocalAudioSection) {
  await withStore("readwrite", (store) => store.put(section));
}

export async function updateLocalSection(
  localSectionId: string,
  updates: Partial<LocalAudioSection>
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
  localSectionId: string
): Promise<LocalAudioSection | undefined> {
  return withStore<LocalAudioSection>("readonly", (store) =>
    store.get(localSectionId)
  );
}

export async function listPendingSections(
  encounterId?: number
): Promise<LocalAudioSection[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.getAll();
    request.onsuccess = () => {
      const sections = (request.result as LocalAudioSection[])
        .filter((section) => section.status !== "registered")
        .filter((section) =>
          encounterId ? section.encounter_id === encounterId : true
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
  const withoutBlob: Omit<LocalAudioSection, "blob"> = {
    local_section_id: current.local_section_id,
    recording_session_id: current.recording_session_id,
    encounter_id: current.encounter_id,
    document_id: current.document_id,
    section_index: current.section_index,
    start_time_ms: current.start_time_ms,
    end_time_ms: current.end_time_ms,
    overlap_ms: current.overlap_ms,
    content_type: current.content_type,
    status: current.status,
    retry_count: current.retry_count,
    gcs_object_name: current.gcs_object_name,
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
