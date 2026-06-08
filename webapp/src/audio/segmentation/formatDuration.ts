export function formatDurationMs(value: number): string {
  const totalSeconds = Math.max(0, Math.round(value / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds
    .toString()
    .padStart(2, "0")}`;
}

export function formatSegmentStateLabel(
  state: string,
  usedFallback: boolean,
): string {
  if (usedFallback) {
    return "Modo compatibilidad";
  }
  switch (state) {
    case "collecting":
      return "Escuchando";
    case "eligibleForCut":
      return "Esperando pausa para cerrar";
    case "closingSoon":
      return "Esperando pausa corta";
    case "finalizing":
      return "Procesando sección";
    case "fallback":
      return "Modo compatibilidad";
    case "initializing":
      return "Inicializando";
    default:
      return "En espera";
  }
}

export const CUT_REASON_LABELS: Record<string, string> = {
  silence_after_minimum: "Pausa tras mínimo de voz",
  closing_soon_silence: "Pausa corta (cierre próximo)",
  forced_maximum: "Corte forzado al máximo",
  wall_clock_limit: "Límite de tiempo real",
  manual_stop: "Detención manual",
  fallback: "Segmentación de compatibilidad",
};
