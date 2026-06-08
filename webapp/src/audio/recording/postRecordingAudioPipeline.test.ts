import { describe, expect, it } from "vitest";

import {
  RETAINED_SEGMENT_JOIN_SILENCE_MS,
  trimMonoSamples,
} from "./postRecordingAudioPipeline";

describe("trimMonoSamples", () => {
  it("inserts configured silence between retained segments", () => {
    const samples = new Float32Array(32_000).fill(1);
    const trimmed = trimMonoSamples(samples, [
      { startMs: 0, endMs: 500 },
      { startMs: 1_500, endMs: 2_000 },
    ]);

    const expectedSpeechSamples = 16_000;
    const expectedGapSamples = 16 * RETAINED_SEGMENT_JOIN_SILENCE_MS;

    expect(trimmed.length).toBe(expectedSpeechSamples + expectedGapSamples);
    expect(trimmed[8_000]).toBe(0);
    expect(trimmed[8_000 + expectedGapSamples - 1]).toBe(0);
  });
});
