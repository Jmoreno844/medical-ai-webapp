import { useCallback, useState } from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { AxiosError } from "axios";
import { logger } from "@/lib/logger";

export interface Patient {
  id: number;
  name: string;
  summary?: string | null;
}

interface ApiErrorResponse {
  message?: string;
  error?: string;
  detail?: string;
}

export const usePatients = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getErrorMessage = useCallback((error: unknown): string => {
    if (error instanceof AxiosError) {
      const errorData = error.response?.data as ApiErrorResponse | undefined;
      return (
        errorData?.message ||
        errorData?.error ||
        errorData?.detail ||
        `Error: ${error.response?.status}`
      );
    }
    return error instanceof Error ? error.message : "Error desconocido";
  }, []);

  const searchPatients = useCallback(async (query: string): Promise<Patient[]> => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await axiosInstance.get(
        `/api/v1/patients/search?name=${encodeURIComponent(query)}`
      );

      if (!Array.isArray(response.data)) {
        logger.warn(
          "Expected array response from patient search:",
          response.data
        );
        return [];
      }

      return response.data;
    } catch (err) {
      logger.error("Error searching patients:", err);
      setError(getErrorMessage(err));
      return [];
    } finally {
      setIsLoading(false);
    }
  }, [getErrorMessage]);

  const createPatient = useCallback(async (patientName: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await axiosInstance.post("/api/v1/patients", {
        name: patientName,
      });

      return response.data;
    } catch (err) {
      logger.error("Error creating patient:", err);
      setError(getErrorMessage(err));
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [getErrorMessage]);

  const updatePatient = useCallback(async (
    patientId: number,
    patientName: string
  ): Promise<boolean> => {
    if (!patientId) {
      setError("No se especificó un ID de paciente válido");
      return false;
    }

    setIsLoading(true);
    setError(null);

    try {
      await axiosInstance.put(`/api/v1/patients/${patientId}`, {
        name: patientName,
      });

      return true;
    } catch (err) {
      logger.error("Error updating patient:", err);
      setError(getErrorMessage(err));
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [getErrorMessage]);

  const deletePatient = useCallback(async (patientId: number): Promise<boolean> => {
    if (!patientId) {
      setError("No se especificó un ID de paciente válido");
      return false;
    }

    setIsLoading(true);
    setError(null);

    try {
      await axiosInstance.delete(`/api/v1/patients/${patientId}`);
      return true;
    } catch (err) {
      logger.error("Error deleting patient:", err);
      setError(getErrorMessage(err));
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [getErrorMessage]);

  return {
    searchPatients,
    createPatient,
    updatePatient,
    deletePatient,
    isLoading,
    error,
  };
};
