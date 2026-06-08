export type EncounterActivityKind =
  | "idle"
  | "recording"
  | "paused"
  | "transcribing"
  | "generating"
  | "transcription_error"
  | "generation_error";

export type EncounterActivityStatus = {
  kind: EncounterActivityKind;
  label: string;
  showBadge: boolean;
  showPing: boolean;
  dotClassName: string;
  pingClassName: string;
  textClassName: string;
};

export type ResolveEncounterActivityStatusInput = {
  isRecording: boolean;
  isPaused: boolean;
  pendingAudioSections: number;
  isTranscribing: boolean;
  transcriptionStatus: "idle" | "pending" | "success" | "error";
  isGenerating: boolean;
  generationError?: string | null;
};

const IDLE_STATUS: EncounterActivityStatus = {
  kind: "idle",
  label: "",
  showBadge: false,
  showPing: false,
  dotClassName: "",
  pingClassName: "",
  textClassName: "",
};

function hasTranscriptionPipelineWork(
  input: ResolveEncounterActivityStatusInput,
): boolean {
  return (
    input.pendingAudioSections > 0 ||
    input.isTranscribing ||
    input.transcriptionStatus === "pending"
  );
}

function resolveDotAndPingClasses(
  kind: EncounterActivityKind,
  hasPipelineWork: boolean,
): Pick<EncounterActivityStatus, "dotClassName" | "pingClassName"> {
  if (kind === "transcription_error" || kind === "generation_error") {
    return { dotClassName: "bg-red-500", pingClassName: "bg-red-400" };
  }

  if (kind === "paused") {
    return { dotClassName: "bg-slate-400", pingClassName: "bg-slate-300" };
  }

  if (
    kind === "transcribing" ||
    kind === "generating" ||
    (kind === "recording" && hasPipelineWork)
  ) {
    return { dotClassName: "bg-purple-500", pingClassName: "bg-purple-400" };
  }

  if (kind === "recording") {
    return { dotClassName: "bg-teal-500", pingClassName: "bg-teal-400" };
  }

  return { dotClassName: "", pingClassName: "" };
}

export function resolveEncounterActivityStatus(
  input: ResolveEncounterActivityStatusInput,
): EncounterActivityStatus {
  const pipelineWork = hasTranscriptionPipelineWork(input);

  const isTranscriptionError =
    !input.isRecording && input.transcriptionStatus === "error";
  const isGenerationError = Boolean(input.generationError?.trim());

  let kind: EncounterActivityKind = "idle";
  let label = "";

  if (isTranscriptionError) {
    kind = "transcription_error";
    label = "Error de transcripción";
  } else if (input.isRecording && input.isPaused) {
    kind = "paused";
    label = "Pausado";
  } else if (input.isRecording) {
    kind = "recording";
    label = "Grabando";
  } else if (pipelineWork) {
    kind = "transcribing";
    label = "Transcribiendo";
  } else if (input.isGenerating) {
    kind = "generating";
    label = "Generando documento";
  } else if (isGenerationError) {
    kind = "generation_error";
    label = "Error al generar";
  }

  if (kind === "idle") {
    return IDLE_STATUS;
  }

  const { dotClassName, pingClassName } = resolveDotAndPingClasses(
    kind,
    pipelineWork,
  );

  const isErrorKind =
    kind === "transcription_error" || kind === "generation_error";

  return {
    kind,
    label,
    showBadge: true,
    showPing: !input.isPaused && !isErrorKind,
    dotClassName,
    pingClassName,
    textClassName: isErrorKind ? "text-red-700" : "text-slate-800",
  };
}
