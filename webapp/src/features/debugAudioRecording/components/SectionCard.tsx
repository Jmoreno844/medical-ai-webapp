import { useState } from "react";
import { Badge } from "@/commons/components/ui/badge";
import { Button } from "@/commons/components/ui/button";
import { Card } from "@/commons/components/ui/card";
import type { RecordedSection } from "@/audio/recording/AudioRecorderController";
import {
  CUT_REASON_LABELS,
  formatDurationMs,
} from "@/audio/segmentation/formatDuration";
import { Download } from "lucide-react";

type SectionCardProps = {
  section: RecordedSection;
  index: number;
};

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function SectionCard({ section, index }: SectionCardProps) {
  const [showMetadataJson, setShowMetadataJson] = useState(false);
  const { metadata } = section;
  const cutLabel =
    CUT_REASON_LABELS[metadata.cutReason] ?? metadata.cutReason;

  return (
    <Card className="border border-slate-200 p-5">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{`Sección ${index + 1}`}</Badge>
            <Badge variant="outline">#{metadata.sequence}</Badge>
            <Badge variant="outline">
              Real: {formatDurationMs(metadata.wallClockDurationMs)}
            </Badge>
            <Badge variant="outline">
              Voz: {formatDurationMs(metadata.speechDurationMs)}
            </Badge>
            <Badge variant="secondary">{cutLabel}</Badge>
            {metadata.forcedCut ? (
              <Badge className="bg-red-600 text-white">Corte forzado</Badge>
            ) : null}
            {metadata.overlapBeforeMs > 0 ? (
              <Badge variant="outline">
                Overlap: {metadata.overlapBeforeMs} ms
              </Badge>
            ) : null}
          </div>
          <audio controls src={section.url} className="h-10 w-full max-w-md" />
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              downloadBlob(
                section.blob,
                `section-${metadata.sequence}.webm`,
              )
            }
          >
            <Download className="mr-2 h-4 w-4" />
            Audio
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowMetadataJson((current) => !current)}
          >
            {showMetadataJson ? "Ocultar JSON" : "Ver JSON"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              const json = JSON.stringify(metadata, null, 2);
              downloadBlob(
                new Blob([json], { type: "application/json" }),
                `section-${metadata.sequence}.json`,
              );
            }}
          >
            <Download className="mr-2 h-3.5 w-3.5" />
            JSON
          </Button>
          <Badge variant="outline" className="text-[11px] text-slate-600">
            {metadata.vadAvailable ? "Silero" : "Fallback"}
            {metadata.vadModelVersion
              ? ` (${metadata.vadModelVersion})`
              : ""}
          </Badge>
          <Badge variant="outline" className="text-[11px] text-slate-500">
            {metadata.audioMimeType}
          </Badge>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-md border border-slate-200 bg-white p-3">
            <p className="text-sm font-medium text-slate-900">Frontend guardó</p>
            <p className="mt-1 text-xs text-slate-600">
              Blob original + tiempos de voz + silencios candidatos.
            </p>
          </div>
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <p className="text-sm font-medium text-slate-900">
              Backend usaría después
            </p>
            <p className="mt-1 text-xs text-slate-600">
              Estos silencios son solo sugerencias; el recorte real del audio se
              haría fuera del navegador.
            </p>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs">
            <p className="mb-2 font-medium text-slate-900">Intervalos de voz</p>
            {metadata.speechIntervals.length === 0 ? (
              <p className="text-slate-500">Sin intervalos registrados.</p>
            ) : (
              <ul className="space-y-1 text-slate-700">
                {metadata.speechIntervals.map((interval) => (
                  <li key={`${interval.startMs}-${interval.endMs}`}>
                    {formatDurationMs(interval.startMs)} –{" "}
                    {formatDurationMs(interval.endMs)} (
                    {formatDurationMs(interval.endMs - interval.startMs)})
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs">
            <p className="mb-2 font-medium text-slate-900">
              Silencios removibles (≥ 3 s)
            </p>
            {metadata.removableSilences.length === 0 ? (
              <p className="text-slate-500">Ninguno detectado.</p>
            ) : (
              <ul className="space-y-1 text-slate-700">
                {metadata.removableSilences.map((silence) => (
                  <li key={`${silence.startMs}-${silence.endMs}`}>
                    {formatDurationMs(silence.startMs)} –{" "}
                    {formatDurationMs(silence.endMs)} (
                    {formatDurationMs(silence.endMs - silence.startMs)})
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {showMetadataJson ? (
          <pre className="max-h-48 overflow-auto rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-700">
            {JSON.stringify(metadata, null, 2)}
          </pre>
        ) : null}
      </div>
    </Card>
  );
}
