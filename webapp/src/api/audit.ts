import axiosInstance from "@/commons/utils/axiosInstance";
import { logger } from "@/lib/logger";

type ClientAuditAction =
  | "document.copied"
  | "document.downloaded"
  | "document.exported";

type ClientAuditPayload = {
  action: ClientAuditAction;
  patient_id?: number | null;
  encounter_id?: number | null;
  document_id?: number | null;
};

export async function postClientAuditEvent(
  payload: ClientAuditPayload,
): Promise<void> {
  try {
    await axiosInstance.post("/api/v1/audit/client-events", payload);
  } catch (error) {
    logger.warn("[audit] failed to post client audit event", {
      action: payload.action,
      documentId: payload.document_id,
      encounterId: payload.encounter_id,
      error,
    });
  }
}
