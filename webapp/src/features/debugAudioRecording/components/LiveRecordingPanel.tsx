import { Badge } from "@/commons/components/ui/badge";
import { Button } from "@/commons/components/ui/button";
import { Card } from "@/commons/components/ui/card";
import type { LiveRecordingState } from "@/audio/recording/AudioRecorderController";
import {
  formatDurationMs,
  formatSegmentStateLabel,
} from "@/audio/segmentation/formatDuration";
import { Loader2, Mic, Pause, Play, Square } from "lucide-react";

type LiveRecordingPanelProps = {
  liveState: LiveRecordingState;
  error: string | null;
  showVadDebug: boolean;
  onToggleVadDebug: () => void;
  onStart: () => void;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
  onClear: () => void;
};

export function LiveRecordingPanel({
  liveState,
  error,
  showVadDebug,
  onToggleVadDebug,
  onStart,
  onStop,
  onPause,
  onResume,
  onClear,
}: LiveRecordingPanelProps) {
  const statusLabel = liveState.isInitializing
    ? "Cargando Silero VAD…"
    : liveState.isPaused
    ? "Pausado"
    : liveState.isRecording
      ? liveState.speechDurationMs > 0 &&
          liveState.segmentState === "collecting"
        ? "Voz detectada"
        : formatSegmentStateLabel(
            liveState.segmentState,
            liveState.usedFallback,
          )
      : "En espera";

  return (
    <Card className="border border-slate-200 p-5">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            onClick={liveState.isRecording ? onStop : onStart}
            disabled={
              liveState.isInitializing ||
              (liveState.isPaused && !liveState.isRecording)
            }
          >
            {liveState.isInitializing ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Inicializando…
              </>
            ) : liveState.isRecording ? (
              <>
                <Square className="mr-2 h-4 w-4" />
                Detener
              </>
            ) : (
              <>
                <Mic className="mr-2 h-4 w-4" />
                Grabar
              </>
            )}
          </Button>

          {liveState.isRecording ? (
            <Button
              size="sm"
              variant="outline"
              onClick={liveState.isPaused ? onResume : onPause}
            >
              {liveState.isPaused ? (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Reanudar
                </>
              ) : (
                <>
                  <Pause className="mr-2 h-4 w-4" />
                  Pausar
                </>
              )}
            </Button>
          ) : null}

          <Button
            size="sm"
            variant="outline"
            onClick={onClear}
            disabled={liveState.isRecording}
          >
            Limpiar secciones
          </Button>

          <Button variant="ghost" size="sm" onClick={onToggleVadDebug}>
            {showVadDebug ? "Ocultar VAD" : "Ver VAD"}
          </Button>
        </div>

        <div className="flex flex-wrap gap-2">
          <Badge variant={liveState.isRecording ? "default" : "secondary"}>
            {statusLabel}
          </Badge>
          <Badge variant="outline">
            Real: {formatDurationMs(liveState.wallClockDurationMs)}
          </Badge>
          <Badge variant="outline">
            Voz: {formatDurationMs(liveState.speechDurationMs)}
          </Badge>
          <Badge variant="outline">
            Silencio: {Math.round(liveState.currentSilenceMs)} ms
          </Badge>
          <Badge variant="outline">
            Secciones: {liveState.sectionCount}
          </Badge>
          <Badge variant={liveState.vadAvailable ? "secondary" : "outline"}>
            {liveState.vadAvailable ? "Silero VAD" : "Fallback RMS"}
          </Badge>
        </div>

        {liveState.initWarning ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {liveState.initWarning}
          </div>
        ) : null}

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        {showVadDebug && liveState.lastSpeechProbability !== undefined ? (
          <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
            Probabilidad VAD: {liveState.lastSpeechProbability.toFixed(4)} |
            Estado FSM: {liveState.segmentState}
          </div>
        ) : null}

        <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <p>
            <span className="font-medium text-slate-800">Frontend:</span> graba
            y marca silencios posibles.
          </p>
          <p>
            <span className="font-medium text-slate-800">Backend:</span> recorta
            el audio real más adelante, no en esta pantalla.
          </p>
        </div>
      </div>
    </Card>
  );
}
