import React from "react";

interface DocumentGenerationProgressProps {
  isGenerating: boolean;
  content: string;
  isComplete: boolean;
  error: string | null;
  onViewDocument?: () => void;
}

export const DocumentGenerationProgress: React.FC<
  DocumentGenerationProgressProps
> = ({ isGenerating, content, isComplete, error, onViewDocument }) => {
  if (!isGenerating && !content && !error && !isComplete) {
    return null;
  }

  const title = isComplete
    ? "Documento generado"
    : error
      ? "Falló la generación"
      : "Generando nota clínica en otro documento…";

  const detail = error
    ? error
    : isComplete
      ? "La nota ya está lista para revisión."
      : "Puedes seguir escribiendo aquí mientras se completa en segundo plano.";

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-slate-900">{title}</p>
          <p className="truncate text-xs text-slate-600">{detail}</p>
        </div>

        <div className="flex items-center gap-2">
          {isGenerating && !error && (
            <div
              className="h-2.5 w-2.5 shrink-0 animate-pulse rounded-full bg-violet-500"
              aria-hidden="true"
            />
          )}

          {onViewDocument && (
            <button
              onClick={onViewDocument}
              className="shrink-0 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-slate-700"
            >
              {error ? "Abrir y reintentar" : isComplete ? "Abrir" : "Ver"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
