export interface Encounter {
  id: number;
  id_medico: number;
  id_paciente?: number;
  nombre_encuentro: string;
  fecha: string; // date will come as string from API
}
