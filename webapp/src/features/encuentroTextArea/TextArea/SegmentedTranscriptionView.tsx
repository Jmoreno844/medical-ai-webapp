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
      <div className="space-y-4">
        {blocks.map((block) => (
          <section
            key={block.sectionId}
            className="grid grid-cols-[72px_minmax(0,1fr)] gap-3 border-b border-slate-100 py-1 last:border-b-0"
          >
            <div className="pt-1 text-xs font-semibold tabular-nums tracking-wide text-slate-500">
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
