import { describe, expect, it } from "vitest";

import { resolveEncounterActivityStatus } from "./resolveEncounterActivityStatus";

const baseInput = {
  isRecording: false,
  isPaused: false,
  pendingAudioSections: 0,
  isTranscribing: false,
  transcriptionStatus: "idle" as const,
  isGenerating: false,
  generationError: null,
};

describe("resolveEncounterActivityStatus", () => {
  it("returns idle when there is no active work", () => {
    const status = resolveEncounterActivityStatus(baseInput);

    expect(status.kind).toBe("idle");
    expect(status.showBadge).toBe(false);
  });

  it("shows Grabando with a teal dot when recording without pipeline work", () => {
    const status = resolveEncounterActivityStatus({
      ...baseInput,
      isRecording: true,
    });

    expect(status.label).toBe("Grabando");
    expect(status.kind).toBe("recording");
    expect(status.dotClassName).toBe("bg-teal-500");
    expect(status.pingClassName).toBe("bg-teal-400");
    expect(status.showPing).toBe(true);
  });

  it("shows Grabando with a purple dot when recording with pipeline work", () => {
    const status = resolveEncounterActivityStatus({
      ...baseInput,
      isRecording: true,
      pendingAudioSections: 2,
    });

    expect(status.label).toBe("Grabando");
    expect(status.kind).toBe("recording");
    expect(status.dotClassName).toBe("bg-purple-500");
    expect(status.pingClassName).toBe("bg-purple-400");
  });

  it("shows Transcribiendo with purple when pending sections exist without recording", () => {
    const status = resolveEncounterActivityStatus({
      ...baseInput,
      pendingAudioSections: 1,
    });

    expect(status.label).toBe("Transcribiendo");
    expect(status.kind).toBe("transcribing");
    expect(status.dotClassName).toBe("bg-purple-500");
    expect(status.showPing).toBe(true);
  });

  it("shows Transcribiendo when backend transcription is in progress", () => {
    const status = resolveEncounterActivityStatus({
      ...baseInput,
      isTranscribing: true,
      transcriptionStatus: "pending",
    });

    expect(status.label).toBe("Transcribiendo");
    expect(status.kind).toBe("transcribing");
  });

  it("shows Generando documento when generation is active", () => {
    const status = resolveEncounterActivityStatus({
      ...baseInput,
      isGenerating: true,
    });

    expect(status.label).toBe("Generando documento");
    expect(status.kind).toBe("generating");
    expect(status.dotClassName).toBe("bg-purple-500");
    expect(status.showPing).toBe(true);
  });

  it("prioritizes transcribing over generating when both are active", () => {
    const status = resolveEncounterActivityStatus({
      ...baseInput,
      isTranscribing: true,
      transcriptionStatus: "pending",
      isGenerating: true,
    });

    expect(status.label).toBe("Transcribiendo");
    expect(status.kind).toBe("transcribing");
  });

  it("shows Pausado without ping when recording is paused", () => {
    const status = resolveEncounterActivityStatus({
      ...baseInput,
      isRecording: true,
      isPaused: true,
      pendingAudioSections: 1,
    });

    expect(status.label).toBe("Pausado");
    expect(status.kind).toBe("paused");
    expect(status.dotClassName).toBe("bg-slate-400");
    expect(status.showPing).toBe(false);
  });

  it("shows transcription error when not recording", () => {
    const status = resolveEncounterActivityStatus({
      ...baseInput,
      transcriptionStatus: "error",
    });

    expect(status.label).toBe("Error de transcripción");
    expect(status.kind).toBe("transcription_error");
    expect(status.textClassName).toBe("text-red-700");
    expect(status.showPing).toBe(false);
  });

  it("prioritizes recording over transcription error while mic is active", () => {
    const status = resolveEncounterActivityStatus({
      ...baseInput,
      isRecording: true,
      transcriptionStatus: "error",
    });

    expect(status.label).toBe("Grabando");
    expect(status.kind).toBe("recording");
  });

  it("shows generation error only when no other activity is active", () => {
    const status = resolveEncounterActivityStatus({
      ...baseInput,
      generationError: "Falló la generación",
    });

    expect(status.label).toBe("Error al generar");
    expect(status.kind).toBe("generation_error");
    expect(status.showPing).toBe(false);
  });
});
