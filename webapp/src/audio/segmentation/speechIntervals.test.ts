import { describe, expect, it } from "vitest";

import {
  RETAINED_AUDIO_PADDING_MS,
  buildRetainedIntervals,
} from "./speechIntervals";

describe("buildRetainedIntervals", () => {
  it("adds padding around retained audio segments", () => {
    const retained = buildRetainedIntervals(
      [{ startMs: 2_000, endMs: 6_000 }],
      10_000,
    );

    expect(retained).toEqual([
      {
        startMs: 0,
        endMs: 2_000 + RETAINED_AUDIO_PADDING_MS,
      },
      {
        startMs: 6_000 - RETAINED_AUDIO_PADDING_MS,
        endMs: 10_000,
      },
    ]);
  });

  it("merges retained intervals when padding makes them overlap", () => {
    const retained = buildRetainedIntervals(
      [{ startMs: 1_000, endMs: 1_500 }],
      3_000,
      300,
    );

    expect(retained).toEqual([{ startMs: 0, endMs: 3_000 }]);
  });
});
