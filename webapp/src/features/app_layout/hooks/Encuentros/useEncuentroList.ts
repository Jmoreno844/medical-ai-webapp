import { useState, useEffect } from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { Encuentro } from "@/types/encuentroList";
import { logger } from "@/lib/logger";

export const useEncuentroList = () => {
  const [encuentros, setEncuentros] = useState<Encuentro[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEncuentros = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axiosInstance.get("/api/encounters");
      setEncuentros(response.data);
    } catch (err) {
      logger.error("Error fetching encuentros:", err);
      setError("Error al cargar los encuentros");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEncuentros();
  }, []);

  return {
    encuentros,
    loading,
    error,
    refetch: fetchEncuentros,
  };
};

export default useEncuentroList;
