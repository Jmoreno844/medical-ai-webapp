import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/commons/components/ui/tabs";
import CopilotDebugPanel from "@/features/copilotChat/CopilotDebugPanel";
import CopilotSideChatPanel from "@/features/copilotChat/CopilotSideChatPanel";
import { useCopilotPanelController } from "@/features/copilotChat/useCopilotPanelController";

type CopilotSidePanelProps = {
  encounterId: number;
};

export default function CopilotSidePanel({
  encounterId,
}: CopilotSidePanelProps) {
  const controller = useCopilotPanelController(encounterId);

  return (
    <Tabs
      defaultValue="copilot"
      className="flex h-full min-h-0 flex-col rounded-md border bg-slate-50 p-3"
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Copilot Panel</h2>
          <p className="text-xs text-slate-600">
            Alterna entre la vista conversacional y la vista tecnica del copiloto.
          </p>
        </div>
        <TabsList className="grid w-[200px] grid-cols-2">
          <TabsTrigger value="copilot">Copilot</TabsTrigger>
          <TabsTrigger value="debug">Debug</TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="copilot" className="min-h-0 flex-1">
        <CopilotSideChatPanel controller={controller} />
      </TabsContent>

      <TabsContent value="debug" className="min-h-0 flex-1">
        <div className="h-full min-h-0 overflow-y-auto">
          <CopilotDebugPanel encounterId={encounterId} controller={controller} />
        </div>
      </TabsContent>
    </Tabs>
  );
}
