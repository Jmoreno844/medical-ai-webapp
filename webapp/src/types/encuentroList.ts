export interface Encuentro {
  id: number;
  doctor_id: number;
  patient_id?: number;
  encounter_name: string;
  occurred_at: string;
}
