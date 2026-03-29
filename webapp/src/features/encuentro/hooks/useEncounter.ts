import { useState } from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { AxiosError } from "axios";
import { logger } from "@/lib/logger";

/**
 * Interface for encounter update data
 */
interface EncounterUpdateData {
  patient_id?: number | null;
  encounter_name?: string;
  patient_connected?: boolean;
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
      // Create a payload that only includes non-undefined values
      const payload: Record<string, unknown> = {};

      if (updateData.patient_id !== undefined) {
        payload.patient_id = updateData.patient_id;
      }

      if (updateData.encounter_name !== undefined) {
        payload.encounter_name = updateData.encounter_name;
      }

      if (updateData.patient_connected !== undefined) {
        payload.patient_connected = updateData.patient_connected;
      }

      logger.debug(
        `Updating encounter ${encounterIdToUpdate} with:`,
        JSON.stringify(payload)
      );

      // Log the exact payload being sent for debugging
      logger.debug("Raw payload:", payload);

      const response = await axiosInstance.patch(
        `/api/encounters/${encounterIdToUpdate}`,
        payload,
        {
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      logger.debug("Update response:", response.data);
      return true;
    } catch (err) {
      const errorMessage = getErrorMessage(err);
      setError(errorMessage);

      // More detailed error logging
      if (err instanceof AxiosError) {
        logger.error("Error updating encounter:", {
          status: err.response?.status,
          statusText: err.response?.statusText,
          data: err.response?.data,
          message: errorMessage,
        });
      } else {
        logger.error("Error updating encounter:", errorMessage, err);
      }

      return false;
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Deletes an encounter
   *
   * @param encounterIdToDelete - The ID of the encounter to delete
   * @returns An object with success flag and data if available
   */
  const deleteEncounter = async (
    encounterIdToDelete: number = encounterId || 0
  ): Promise<{ success: boolean; data?: any }> => {
    if (!encounterIdToDelete) {
      setError("No se especificó un ID de encuentro para eliminar");
      return { success: false };
    }

    setIsLoading(true);
    setError(null);

    try {
      logger.debug(`Deleting encounter ${encounterIdToDelete}`);

      const response = await axiosInstance.delete(
        `/api/encounters/${encounterIdToDelete}`
      );

      logger.debug("Delete response:", response.data);

      // Check if the response contains a success indicator
      const success = response.data?.success === true;

      return {
        success,
        data: response.data,
      };
    } catch (err) {
      const errorMessage = getErrorMessage(err);
      setError(errorMessage);

      // More detailed error logging
      if (err instanceof AxiosError) {
        logger.error("Error deleting encounter:", {
          status: err.response?.status,
          statusText: err.response?.statusText,
          data: err.response?.data,
          message: errorMessage,
        });
      } else {
        logger.error("Error deleting encounter:", errorMessage, err);
      }

      return { success: false };
    } finally {
      setIsLoading(false);
    }
  };

  return {
    updateEncounter,
    deleteEncounter,
    isLoading,
    error,
  };
};
