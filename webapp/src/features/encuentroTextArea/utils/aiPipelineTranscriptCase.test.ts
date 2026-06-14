import { describe, expect, it } from "vitest";
import {
  buildAiPipelineCaseFromBlocks,
  parseAiPipelineTranscriptCaseFile,
} from "./aiPipelineTranscriptCase";

describe("aiPipelineTranscriptCase", () => {
  it("builds export JSON with sequential turn_id values", () => {
    const transcriptCase = buildAiPipelineCaseFromBlocks(
      [
        {
          sectionId: "s0",
          startTimeMs: 0,
          endTimeMs: 60_000,
          turns: [
            {
              speaker: "MEDICO",
              text: "Hola",
              overlaps_previous: false,
              overlaps_next: false,
            },
            {
              speaker: "PACIENTE",
              text: "Buenos días",
              overlaps_previous: false,
              overlaps_next: false,
            },
          ],
          text: "",
          status: "transcribed",
        },
      ],
      "case1",
    );

    expect(transcriptCase).toEqual({
      session_id: "case1",
      language: "es",
      chunks: [
        {
          chunk_id: "s0",
          turns: [
            { turn_id: 0, speaker: "MEDICO", text: "Hola" },
            { turn_id: 1, speaker: "PACIENTE", text: "Buenos días" },
          ],
        },
      ],
    });
  });

  it("accepts index entry shape with transcript_json", () => {
    const parsed = parseAiPipelineTranscriptCaseFile({
      id: "case3",
      transcript_json: {
        session_id: "case3",
        chunks: [
          {
            chunk_id: "s0",
            turns: [{ turn_id: 0, speaker: "MEDICO", text: "Hola" }],
          },
        ],
      },
    });

    expect(parsed.session_id).toBe("case3");
    expect(parsed.chunks[0].turns[0].text).toBe("Hola");
  });
});
