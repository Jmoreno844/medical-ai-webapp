/**
 * Represents a medical encounter in the system
 */
export interface Encuentro {
  id: number;
  nombre_encuentro: string;
  fecha: string;
  estado: string;
  tipo_encuentro: string;
  notas?: string;
  paciente_conectado: boolean;
  paciente_id?: number;
  medico_id?: number;
  created_at?: string;
  updated_at?: string;
}
