import axiosInstance from "@/commons/utils/axiosInstance";
import { Encuentro } from "@/types/encuentroList";

/**
 * Fetches all encounters for a specific doctor
 * @returns Promise with an array of encounters
 */
export const getDoctorEncounters = async (): Promise<Encuentro[]> => {
  try {
    const response = await axiosInstance.get<Encuentro[]>(`/api/encuentros`);
    return response.data;
  } catch (error) {
    console.error("Error fetching doctor encounters:", error);
    throw error;
  }
};

/**
 * Fetches a single encounter by ID
 * @param encounterId - The ID of the encounter
 * @returns Promise with the encounter data
 */
export const getEncounterById = async (
  encounterId: number
): Promise<Encuentro> => {
  try {
    const response = await axiosInstance.get<Encuentro>(
      `/api/encuentros/${encounterId}`
    );
    return response.data;
  } catch (error) {
    console.error("Error fetching encounter details:", error);
    throw error;
  }
};
