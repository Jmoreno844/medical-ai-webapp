/**
 * Represents a medical encounter in the system (API-aligned).
 */
export interface Encuentro {
  id: number;
  encounter_name: string;
  occurred_at: string;
  estado?: string;
  tipo_encuentro?: string;
  notas?: string;
  patient_connected: boolean;
  patient_id?: number;
  doctor_id?: number;
  created_at?: string;
  updated_at?: string;
  has_been_transcribed?: boolean;
  nombre_paciente?: string;
}
