import { describe, expect, it } from "vitest";
import { SpeechSegmenter } from "./SpeechSegmenter";
import { detectRemovableSilences } from "./speechIntervals";
import { SEGMENTATION_CONFIG } from "./segmentationConfig";
import type { VadFrame } from "../vad/VadAdapter";

function emitSegment(
  segmenter: SpeechSegmenter,
  options: {
    speechMs?: number;
    silenceMs?: number;
    startMs?: number;
    chunkMs?: number;
    isSpeech?: boolean;
  },
): number {
  const {
    speechMs = 0,
    silenceMs = 0,
    startMs = 0,
    chunkMs = 100,
  } = options;

  let timestampMs = startMs;
  let remaining = speechMs + silenceMs;
  let speechRemaining = speechMs;

  while (remaining > 0) {
    const durationMs = Math.min(chunkMs, remaining);
    const frameIsSpeech = speechRemaining > 0;
    const frame: VadFrame = {
      timestampMs,
      durationMs,
      speechProbability: frameIsSpeech ? 0.9 : 0.1,
      isSpeech: frameIsSpeech,
    };
    segmenter.processFrame(frame);
    timestampMs += durationMs;
    remaining -= durationMs;
    if (speechRemaining > 0) {
      speechRemaining -= durationMs;
    }
  }

  return timestampMs;
}

describe("SpeechSegmenter", () => {
  it("1. 19s speech + 10s silence does not close before minimum", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    const endMs = emitSegment(segmenter, {
      speechMs: 19_000,
      silenceMs: 10_000,
    });
    expect(endMs).toBe(29_000);
    expect(segmenter.getSnapshot().speechDurationMs).toBe(19_000);
    expect(segmenter.getSnapshot().state).toBe("collecting");
  });

  it("2. 20s speech + 1.4s silence does not close", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    emitSegment(segmenter, { speechMs: 20_000, silenceMs: 1_400 });
    expect(segmenter.getSnapshot().state).not.toBe("stopped");
    const cut = segmenter.processFrame({
      timestampMs: 21_400,
      durationMs: 0,
      speechProbability: 0.1,
      isSpeech: false,
    });
    expect(cut).toBeNull();
  });

  it("3. 20s speech + 1.5s silence closes with silence_after_minimum", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    let cutSignal = null as ReturnType<SpeechSegmenter["processFrame"]>;
    emitSegment(segmenter, { speechMs: 20_000, silenceMs: 1_400, startMs: 0 });
    cutSignal = segmenter.processFrame({
      timestampMs: 21_400,
      durationMs: 100,
      speechProbability: 0.1,
      isSpeech: false,
    });
    expect(cutSignal?.cutReason).toBe("silence_after_minimum");
    expect(cutSignal?.forcedCut).toBe(false);
  });

  it("4. 75s continuous speech does not close without silence", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    emitSegment(segmenter, { speechMs: 75_000 });
    expect(segmenter.getSnapshot().speechDurationMs).toBe(75_000);
    expect(segmenter.getSnapshot().state).toBe("eligibleForCut");
  });

  it("5. 75s speech + 1.5s silence closes", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    emitSegment(segmenter, { speechMs: 75_000, silenceMs: 1_400 });
    const cut = segmenter.processFrame({
      timestampMs: 76_400,
      durationMs: 100,
      speechProbability: 0.1,
      isSpeech: false,
    });
    expect(cut?.cutReason).toBe("silence_after_minimum");
  });

  it("6. 87s speech + 500ms silence closes with closing_soon_silence", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    emitSegment(segmenter, { speechMs: 87_000, silenceMs: 400 });
    const cut = segmenter.processFrame({
      timestampMs: 87_400,
      durationMs: 100,
      speechProbability: 0.1,
      isSpeech: false,
    });
    expect(cut?.cutReason).toBe("closing_soon_silence");
  });

  it("7. 90s continuous speech forces cut with overlap", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    let forcedCut: ReturnType<SpeechSegmenter["processFrame"]> = null;
    for (let timestampMs = 0; timestampMs < 90_000; timestampMs += 100) {
      const cut = segmenter.processFrame({
        timestampMs,
        durationMs: 100,
        speechProbability: 0.9,
        isSpeech: true,
      });
      if (cut) {
        forcedCut = cut;
      }
    }
    expect(forcedCut?.cutReason).toBe("forced_maximum");
    expect(forcedCut?.forcedCut).toBe(true);
    expect(forcedCut?.overlapBeforeMs).toBe(
      SEGMENTATION_CONFIG.forcedCutOverlapMs,
    );
  });

  it("8. 180s wall with 15s speech triggers wall_clock_limit", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    let wallCut: ReturnType<SpeechSegmenter["processFrame"]> = null;
    for (let timestampMs = 0; timestampMs < 15_000; timestampMs += 100) {
      segmenter.processFrame({
        timestampMs,
        durationMs: 100,
        speechProbability: 0.9,
        isSpeech: true,
      });
    }
    for (let timestampMs = 15_000; timestampMs < 180_000; timestampMs += 100) {
      const cut = segmenter.processFrame({
        timestampMs,
        durationMs: 100,
        speechProbability: 0.05,
        isSpeech: false,
      });
      if (cut) {
        wallCut = cut;
      }
    }
    expect(wallCut?.cutReason).toBe("wall_clock_limit");
    expect(wallCut?.speechDurationMs).toBe(15_000);
  });

  it("9. fallback mode continues after Silero unavailable", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(false);
    segmenter.enterFallback();
    emitSegment(segmenter, { speechMs: 5_000 });
    expect(segmenter.getSnapshot().state).toBe("fallback");
    expect(segmenter.getSnapshot().speechDurationMs).toBe(5_000);
  });

  it("10. entering fallback mid-session preserves accumulated speech", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    emitSegment(segmenter, { speechMs: 30_000 });
    segmenter.enterFallback();
    emitSegment(segmenter, { speechMs: 10_000, startMs: 30_000 });
    expect(segmenter.getSnapshot().speechDurationMs).toBe(40_000);
    expect(segmenter.getSnapshot().vadAvailable).toBe(false);
  });

  it("11. paused frames are not counted", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    emitSegment(segmenter, { speechMs: 10_000 });
    segmenter.setPaused(true);
    emitSegment(segmenter, { speechMs: 5_000, startMs: 10_000 });
    segmenter.setPaused(false);
    emitSegment(segmenter, { speechMs: 3_000, startMs: 10_000 });
    expect(segmenter.getSnapshot().speechDurationMs).toBe(13_000);
    expect(segmenter.getSnapshot().wallClockDurationMs).toBe(13_000);
  });

  it("12. manual stop with 15s speech emits manual_stop", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    emitSegment(segmenter, { speechMs: 15_000 });
    const cut = segmenter.stop();
    expect(cut?.cutReason).toBe("manual_stop");
    expect(cut?.speechDurationMs).toBe(15_000);
  });

  it("12b. manual stop preserves trailing removable silence", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    emitSegment(segmenter, { speechMs: 1_000, silenceMs: 4_000 });
    const cut = segmenter.stop();
    expect(cut?.cutReason).toBe("manual_stop");
    expect(cut?.wallClockDurationMs).toBe(5_000);
    expect(cut?.removableSilences).toEqual([
      { startMs: 1_000, endMs: 5_000 },
    ]);
  });

  it("13. 2.9s internal silence is not removable", () => {
    const removable = detectRemovableSilences(
      [
        { startMs: 0, endMs: 25_000 },
        { startMs: 27_900, endMs: 60_000 },
      ],
      60_000,
    );
    expect(removable).toHaveLength(0);
  });

  it("14. 3s internal silence is removable", () => {
    const removable = detectRemovableSilences(
      [
        { startMs: 0, endMs: 25_000 },
        { startMs: 28_000, endMs: 64_000 },
      ],
      64_000,
    );
    expect(removable).toHaveLength(1);
    expect(removable[0].endMs - removable[0].startMs).toBeGreaterThanOrEqual(
      3_000,
    );
  });

  it("15. duplicate and out-of-order frames do not double-count speech", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);
    const frame: VadFrame = {
      timestampMs: 1_000,
      durationMs: 100,
      speechProbability: 0.9,
      isSpeech: true,
    };
    segmenter.processFrame(frame);
    segmenter.processFrame(frame);
    segmenter.processFrame({
      ...frame,
      timestampMs: 500,
    });
    emitSegment(segmenter, { speechMs: 1_000, startMs: 1_100 });
    expect(segmenter.getSnapshot().speechDurationMs).toBe(1_100);
  });

  it("16. section cuts reset speech interval timestamps to section-relative time", () => {
    const segmenter = new SpeechSegmenter();
    segmenter.start(true);

    for (let timestampMs = 0; timestampMs < 90_000; timestampMs += 100) {
      const cut = segmenter.processFrame({
        timestampMs,
        durationMs: 100,
        speechProbability: 0.9,
        isSpeech: true,
      });
      if (cut) {
        expect(cut.cutReason).toBe("forced_maximum");
        expect(cut.speechIntervals[0]?.startMs).toBe(0);
        expect(cut.speechIntervals.at(-1)?.endMs).toBeLessThanOrEqual(
          cut.wallClockDurationMs,
        );
      }
    }

    emitSegment(segmenter, { speechMs: 12_000, startMs: 90_000 });
    const secondCut = segmenter.stop();

    expect(secondCut?.cutReason).toBe("manual_stop");
    expect(secondCut?.wallClockDurationMs).toBe(12_000);
    expect(secondCut?.speechIntervals[0]?.startMs).toBe(0);
    expect(secondCut?.speechIntervals.at(-1)?.endMs).toBeLessThanOrEqual(
      secondCut?.wallClockDurationMs ?? 0,
    );
  });
});
