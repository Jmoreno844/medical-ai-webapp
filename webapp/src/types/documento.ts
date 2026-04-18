/** API shape for clinical documents (English wire format). */
export interface DocumentoOut {
  id: number;
  encounter_id: number;
  kind: string;
  doctor_template_id?: number | null;
  doctor_template_name?: string | null;
  content: string;
  content_markdown: string;
  content_json?: Record<string, unknown> | null;
  created_on: string;
  doctor_id: number;
}

/** Spanish labels for document `kind` values from the API. */
export const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  context: "Contexto",
  transcription: "Transcripción",
  template: "Plantilla",
  note: "Nota clínica",
};

export const DOCUMENT_TYPE_LABELS_LONG: Record<string, string> = {
  context: "Contexto",
  transcription: "Transcripción",
  template: "Documento desde plantilla",
  note: "Nota clínica",
};
