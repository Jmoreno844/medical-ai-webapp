export interface DocumentoOut {
  id: number;
  id_encuentro: number;
  tipo: string;
  id_plantilla_doctor?: number;
  contenido: string;
  fecha_creacion: string; // ISO date string
  id_medico: number;
}
