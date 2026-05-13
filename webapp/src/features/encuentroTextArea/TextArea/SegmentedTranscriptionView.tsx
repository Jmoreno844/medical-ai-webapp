import React from "react";
import { TranscriptionBlock } from "@/workspace/types";
import { formatTranscriptionTimestamp } from "@/workspace/utils/transcriptionBlocks";

type SegmentedTranscriptionViewProps = {
  blocks: TranscriptionBlock[];
};

const SegmentedTranscriptionView: React.FC<SegmentedTranscriptionViewProps> = ({
  blocks,
}) => {
  return (
    <div className="h-full overflow-auto bg-white px-4 py-3">
      <div className="mx-auto max-w-4xl space-y-6">
        {blocks.map((block) => (
          <section
            key={block.sectionId}
            className="rounded-lg border border-slate-200 bg-slate-50/55 px-4 py-3"
          >
            <div className="mb-3 text-xs font-semibold tracking-wide text-slate-500">
              [{formatTranscriptionTimestamp(block.startTimeMs)}]
            </div>
            <div className="whitespace-pre-wrap text-[15px] leading-7 text-slate-800">
              {block.text}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
};

export default SegmentedTranscriptionView;
