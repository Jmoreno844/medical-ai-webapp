/**
 * Encuentro (encounter) API — thin wrappers over axiosInstance.
 */
import axiosInstance from "@/commons/utils/axiosInstance";

export function getEncounter(encounterId: number) {
  return axiosInstance.get(`/api/encounters/${encounterId}`);
}

export function patchEncounter(
  encounterId: number,
  payload: Record<string, unknown>
) {
  return axiosInstance.patch(`/api/encounters/${encounterId}`, payload);
}

export function deleteEncounter(encounterId: number) {
  return axiosInstance.delete(`/api/encounters/${encounterId}`);
}
