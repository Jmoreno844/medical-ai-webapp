import { useState, useEffect, useCallback } from "react";
import * as encountersApi from "@/api/encounters";
import { logger } from "@/lib/logger";

/** Single encounter from GET /api/v1/encounters/:id (matches EncuentroContext shape). */
export interface EncuentroDetail {
  id: number;
  encounter_name: string;
  occurred_at: string;
  patient_id?: number;
  patient_name?: string;
  patient_connected?: boolean;
  has_been_transcribed?: boolean;
}

/**
 * Fetch one encounter by id (shared API layer).
 */
export function useEncuentroDetail(encounterId: number) {
  const [encuentro, setEncuentro] = useState<EncuentroDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = useCallback(async () => {
    if (!encounterId) {
      setEncuentro(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { data } = await encountersApi.getEncounter(encounterId);
      setEncuentro(data as EncuentroDetail);
    } catch (e) {
      logger.error("[useEncuentroDetail] fetch error:", e);
      setError("Error al cargar el encuentro");
      setEncuentro(null);
    } finally {
      setLoading(false);
    }
  }, [encounterId]);

  useEffect(() => {
    void fetchDetail();
  }, [fetchDetail]);

  return { encuentro, loading, error, refetch: fetchDetail };
}
