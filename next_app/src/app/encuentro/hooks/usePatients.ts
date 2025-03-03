import { useState } from "react";
import axiosInstance from "../../../utils/axiosInstance";
import { AxiosError } from "axios";

/**
 * Patient data structure returned from API
 * Matches the PacienteResponse schema from the backend
 */
export interface Patient {
  /** Unique identifier for the patient */
  id: number;
  /** Full name of the patient */
  nombre: string;
  /** Optional summary or notes about the patient */
  resumen?: string | null;
}

/**
 * Error response structure from API
 */
interface ApiErrorResponse {
  message?: string;
  error?: string;
  detail?: string;
}

/**
 * Custom hook for patient-related API operations
 *
 * Provides functions for searching, creating, and updating patients
 *
 * @returns Object containing patient operations and state
 */
export const usePatients = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Extract error message from API error response
   */
  const getErrorMessage = (error: unknown): string => {
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
  };

  /**
   * Search for patients by name
   *
   * @param query - Search string to find matching patients
   * @returns Array of matching patients
   */
  const searchPatients = async (query: string): Promise<Patient[]> => {
    setIsLoading(true);
    setError(null);

    try {
      // Call the correct endpoint with the search parameter
      const response = await axiosInstance.get(
        `api/pacientes/search?name=${encodeURIComponent(query)}`
      );

      // Validate the response data
      if (!Array.isArray(response.data)) {
        console.warn(
          "Expected array response from patient search:",
          response.data
        );
        return [];
      }

      return response.data;
    } catch (err) {
      console.error("Error searching patients:", err);
      setError(getErrorMessage(err));
      return [];
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Create a new patient
   *
   * @param patientName - Name of the patient to create
   * @returns Created patient object or null if failed
   */
  const createPatient = async (patientName: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await axiosInstance.post("/paciente", {
        nombre: patientName,
      });

      return response.data;
    } catch (err) {
      console.error("Error creating patient:", err);
      setError(getErrorMessage(err));
      return null;
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Update an existing patient's information
   *
   * @param patientId - ID of the patient to update
   * @param patientName - New name for the patient
   * @returns Boolean indicating success or failure
   */
  const updatePatient = async (
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
      await axiosInstance.put(`/paciente/${patientId}`, {
        nombre: patientName,
      });

      return true;
    } catch (err) {
      console.error("Error updating patient:", err);
      setError(getErrorMessage(err));
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  return {
    searchPatients,
    createPatient,
    updatePatient,
    isLoading,
    error,
  };
};
