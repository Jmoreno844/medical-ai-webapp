import { CopilotChatMessage } from "@/features/copilotChat/types";
import ChatBubble from "@/features/copilotChat/components/ChatBubble";

type ChatMessageListProps = {
  messages: CopilotChatMessage[];
};

export default function ChatMessageList({ messages }: ChatMessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
        Escribe un mensaje para comenzar.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {messages.map((message) => (
        <ChatBubble key={message.id} message={message} />
      ))}
    </div>
  );
}
