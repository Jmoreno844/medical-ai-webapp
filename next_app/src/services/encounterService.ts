import axiosInstance from "@/utils/axiosInstance";
import { Encounter } from "@/types/encounter";

/**
 * Fetches all encounters for a specific doctor
 * @returns Promise with an array of encounters
 */
export const getDoctorEncounters = async (): Promise<Encounter[]> => {
  try {
    const response = await axiosInstance.get<Encounter[]>(`/api/encuentros`);
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
): Promise<Encounter> => {
  try {
    const response = await axiosInstance.get<Encounter>(
      `/api/encuentros/${encounterId}`
    );
    return response.data;
  } catch (error) {
    console.error("Error fetching encounter details:", error);
    throw error;
  }
};
