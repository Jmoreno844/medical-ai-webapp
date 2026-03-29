import { useState, useEffect, useCallback } from "react";
import * as encountersApi from "@/api/encounters";

/** Single encounter from GET /api/encuentros/:id (matches EncuentroContext shape). */
export interface EncuentroDetail {
  id: number;
  nombre_encuentro: string;
  fecha: string;
  id_paciente?: number;
  nombre_paciente?: string;
  paciente_conectado?: boolean;
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
      console.error("[useEncuentroDetail] fetch error:", e);
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
