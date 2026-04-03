import React from "react";
import Editor from "react-simple-code-editor";
import Prism from "prismjs";
import "prismjs/components/prism-markdown";
import "prismjs/themes/prism-coy.css"; // Optional, standard Prism theme
import { CopilotPatchResponse } from "@/features/copilotDebug/types";

interface PatchSetEditorViewProps {
  content: string;
  patches: CopilotPatchResponse[];
}

type Chunk = 
  | { type: "text"; text: string; key: string }
  | { type: "patch"; patch: CopilotPatchResponse; key: string };

export const PatchSetEditorView: React.FC<PatchSetEditorViewProps> = ({ content, patches }) => {
  // Sort patches ascending by start index
  const sortedPatches = [...patches].sort((a, b) => 
    (a.resolvedRange?.start || 0) - (b.resolvedRange?.start || 0)
  );

  const chunks: Chunk[] = [];
  let lastIndex = 0;

  sortedPatches.forEach((patch) => {
    const start = patch.resolvedRange?.start || 0;
    const end = patch.resolvedRange?.end || 0;
    
    if (start > lastIndex) {
      chunks.push({
        type: "text",
        text: content.slice(lastIndex, start),
        key: `text-${lastIndex}`
      });
    }

    chunks.push({
      type: "patch",
      patch,
      key: `patch-${patch.id}`
    });

    lastIndex = Math.max(lastIndex, end);
  });

  if (lastIndex < content.length) {
    chunks.push({
      type: "text",
      text: content.slice(lastIndex),
      key: `text-${lastIndex}`
    });
  }

  // Fallback to basic if PRISM throws
  const highlight = (code: string) => {
    try {
      return Prism.highlight(code || "", Prism.languages.markdown, "markdown");
    } catch {
      return code || "";
    }
  };

  return (
    <div className="patch-set-editor bg-white h-full overflow-y-auto p-4 text-sm font-mono leading-relaxed border rounded-md">
      {chunks.map((chunk) => {
        if (chunk.type === "text") {
          return (
            <div key={chunk.key} className="py-2 whitespace-pre-wrap text-gray-700">
              {chunk.text}
            </div>
          );
        }

        const { patch } = chunk;
        const diffClasses = 
          patch.status === "accepted" ? "border-green-300 shadow-green-100" :
          patch.status === "rejected" ? "border-red-300 shadow-red-100 opacity-50" :
          "border-indigo-300 shadow-indigo-100 ring-2 ring-indigo-200 outline-none";
        
        return (
          <div key={chunk.key} className={`my-4 border rounded-md shadow-sm overflow-hidden transition-all duration-300 ${diffClasses}`}>
            <div className={`px-3 py-1 flex items-center justify-between text-xs border-b ${patch.status === 'accepted' ? 'bg-green-100 text-green-800' : patch.status === 'rejected' ? 'bg-red-100 text-red-800' : 'bg-indigo-100 text-indigo-800'}`}>
              <span className="font-semibold uppercase tracking-wider">Suggested Change - {patch.status}</span>
              <span className="opacity-75 bg-white/50 px-2 py-0.5 rounded">{patch.type || "replace"}</span>
            </div>
            
            {/* Old Text (Red) */}
            {patch.oldText && (
              <div className="bg-red-50 relative flex border-b border-red-100">
                <div className="w-8 shrink-0 bg-red-100/50 text-red-400 select-none flex items-center justify-center border-r border-red-200 font-bold">-</div>
                <div className="flex-1 relative">
                   <Editor
                     value={patch.oldText}
                     onValueChange={() => {}}
                     highlight={highlight}
                     padding={12}
                     readOnly
                     className="text-red-900 font-mono bg-transparent w-full"
                     style={{
                       fontFamily: '"Fira Code", "JetBrains Mono", monospace'
                     }}
                   />
                </div>
              </div>
            )}

            {/* New Text (Green) */}
            {patch.newText && (
              <div className="bg-green-50 relative flex">
                <div className="w-8 shrink-0 bg-green-100/50 text-green-500 select-none flex items-center justify-center border-r border-green-200 font-bold">+</div>
                <div className="flex-1 relative">
                  <Editor
                    value={patch.newText}
                    onValueChange={() => {}}
                    highlight={highlight}
                    padding={12}
                    readOnly
                    className="text-green-900 font-mono bg-transparent w-full"
                    style={{
                      fontFamily: '"Fira Code", "JetBrains Mono", monospace'
                    }}
                  />
                </div>
              </div>
            )}
            
            {/* Rationale */}
            {patch.rationale && (
              <div className="border-t border-indigo-100 bg-indigo-50/50 px-3 py-2 text-indigo-700 italic text-xs">
                 // {patch.rationale}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
