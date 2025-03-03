import { useState } from "react";
import axiosInstance from "../../../utils/axiosInstance";
import { AxiosError } from "axios";

/**
 * Interface for encounter update data
 */
interface EncounterUpdateData {
  id_paciente?: number;
  nombre_encuentro?: string;
  paciente_conectado?: boolean;
}

/**
 * API error response interface
 */
interface ApiErrorResponse {
  message?: string;
  error?: string;
  detail?: string;
}

/**
 * Custom hook for encounter-related API operations
 *
 * @param encounterId - Optional encounter ID to use as default
 * @returns Object containing encounter operations and state
 */
export const useEncounter = (encounterId?: number) => {
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
   * Updates an existing encounter with patient information
   *
   * @param encounterIdToUpdate - The ID of the encounter to update
   * @param updateData - Data to update the encounter with
   * @returns Boolean indicating success or failure
   */
  const updateEncounter = async (
    encounterIdToUpdate: number = encounterId || 0,
    updateData: EncounterUpdateData
  ): Promise<boolean> => {
    if (!encounterIdToUpdate) {
      setError("No se especificó un ID de encuentro para actualizar");
      return false;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Create a new object with the explicit field to ensure it's sent properly
      const payload = {
        id_paciente: updateData.id_paciente,
        nombre_encuentro: updateData.nombre_encuentro,
        // Always explicitly include paciente_conectado with a non-null value
        paciente_conectado:
          updateData.paciente_conectado === false ? false : true,
      };

      console.log(
        `Updating encounter ${encounterIdToUpdate} with:`,
        JSON.stringify(payload)
      );

      // Log the exact payload being sent for debugging
      console.log("Raw payload:", payload);

      const response = await axiosInstance.put(
        `/api/encuentros/${encounterIdToUpdate}`,
        payload,
        {
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      console.log("Update response:", response.data);
      return true;
    } catch (err) {
      const errorMessage = getErrorMessage(err);
      setError(errorMessage);

      // More detailed error logging
      if (err instanceof AxiosError) {
        console.error("Error updating encounter:", {
          status: err.response?.status,
          statusText: err.response?.statusText,
          data: err.response?.data,
          message: errorMessage,
        });
      } else {
        console.error("Error updating encounter:", errorMessage, err);
      }

      return false;
    } finally {
      setIsLoading(false);
    }
  };

  return {
    updateEncounter,
    isLoading,
    error,
  };
};
