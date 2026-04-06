import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Info, ChevronDown, ChevronRight } from "lucide-react";

import { CopilotChatMessage } from "@/features/copilotChat/types";

type ChatBubbleProps = {
  message: CopilotChatMessage;
};

function ToolBubble({ message }: ChatBubbleProps) {
  const [open, setOpen] = useState(false);
  const isLikelyDebugPayload =
    message.content.trim().startsWith("{") || message.content.length > 160;

  if (!isLikelyDebugPayload) {
    return (
      <div className="mr-10">
        <div className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
          <span className="leading-5">{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="mr-10">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-1.5 text-xs text-slate-500 transition-colors hover:bg-slate-200"
      >
        <Info className="h-3 w-3 shrink-0" />
        <span className="truncate">Detalle técnico</span>
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
      </button>
      {open && (
        <pre className="mt-1.5 max-h-40 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-2 text-[11px] text-slate-600 whitespace-pre-wrap">
          {message.content}
        </pre>
      )}
    </div>
  );
}

export default function ChatBubble({ message }: ChatBubbleProps) {
  if (message.role === "system") {
    return <ToolBubble message={message} />;
  }

  if (message.role === "user") {
    return (
      <div className="ml-10 flex justify-end">
        <div className="rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2.5 text-sm text-white">
          {message.content}
        </div>
      </div>
    );
  }

  // assistant
  return (
    <div className="mr-6">
      <div className="rounded-2xl rounded-bl-sm border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-800">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
            ul: ({ children }) => (
              <ul className="mb-2 ml-4 list-disc space-y-0.5 last:mb-0">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="mb-2 ml-4 list-decimal space-y-0.5 last:mb-0">
                {children}
              </ol>
            ),
            code: ({ children }) => (
              <code className="rounded bg-slate-200 px-1 py-0.5 font-mono text-xs">
                {children}
              </code>
            ),
            strong: ({ children }) => (
              <strong className="font-semibold">{children}</strong>
            ),
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
    </div>
  );
}
