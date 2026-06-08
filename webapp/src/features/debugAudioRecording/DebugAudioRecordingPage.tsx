import { useState } from "react";
import { Separator } from "@/commons/components/ui/separator";
import { useSpeechSegmentedRecorder } from "@/hooks/useSpeechSegmentedRecorder";
import { LiveRecordingPanel } from "./components/LiveRecordingPanel";
import { SectionCard } from "./components/SectionCard";

export default function DebugAudioRecordingPage() {
  const [showVadDebug, setShowVadDebug] = useState(false);
  const {
    liveState,
    sections,
    error,
    startRecording,
    stopRecording,
    pauseRecording,
    resumeRecording,
    clearSections,
  } = useSpeechSegmentedRecorder();

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 py-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Debug de grabación (Silero VAD)
        </h1>
        <p className="max-w-3xl text-sm text-slate-600">
          Esta pantalla prueba solo la parte de navegador: micrófono, VAD,
          cortes de sección y metadata local. Aquí todavía no participa el
          backend.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm font-semibold text-slate-900">
            Frontend en esta página
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Graba audio, detecta voz, cierra secciones y calcula intervalos de
            voz o silencios removibles solo como metadata local.
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-semibold text-slate-900">
            Backend en el flujo real
          </p>
          <p className="mt-1 text-sm text-slate-600">
            En producción recibe secciones, las transcribe y aplica el recorte
            real del audio. En esta pantalla de debug no se llama al backend.
          </p>
        </div>
      </div>

      <LiveRecordingPanel
        liveState={liveState}
        error={error}
        showVadDebug={showVadDebug}
        onToggleVadDebug={() => setShowVadDebug((current) => !current)}
        onStart={() => void startRecording()}
        onStop={() => void stopRecording()}
        onPause={pauseRecording}
        onResume={resumeRecording}
        onClear={clearSections}
      />

      <div className="grid gap-4">
        {sections.map((section, index) => (
          <SectionCard key={section.metadata.sectionId} section={section} index={index} />
        ))}
      </div>

      {sections.length === 0 ? (
        <>
          <Separator />
          <p className="text-sm text-slate-500">
            Graba audio y observa cómo se crean secciones cuando la voz efectiva
            alcanza 20 s y aparece una pausa de 1,5 s, o al acercarse a 90 s de
            voz.
          </p>
        </>
      ) : null}
    </div>
  );
}
