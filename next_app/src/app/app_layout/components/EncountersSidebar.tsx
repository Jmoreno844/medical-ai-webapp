import IconButton from "@/components/IconButton";

/**
 * Props for EncountersSidebar component
 * @property {Function} onClose - Callback to handle the sidebar close action
 */
interface EncountersSidebarProps {
  onClose: () => void;
}

/**
 * EncountersSidebar component displays a sidebar for recent encounters.
 * Provides options to interact with individual encounter items.
 * 
 * @param {EncountersSidebarProps} props - Props containing the onClose callback
 * @returns {JSX.Element} The rendered sidebar component
 */
export const EncountersSidebar = ({ onClose }: EncountersSidebarProps) => {
  return (
    <div className="h-screen w-64 bg-white shadow-lg z-40 p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="font-semibold">Ver Encuentros</h2>
        <IconButton
          src="/close_sidebar.svg"
          alt="Close sidebar"
          onClick={onClose}
          size={24}
          className="hover:bg-gray-200"
        />
      </div>
      <div className="space-y-2">
        {/* Example encounter items. In production, these should be dynamic and sanitized. */}
        <div className="p-2 hover:bg-gray-100 cursor-pointer rounded">
          Encuentro #1234
        </div>
        <div className="p-2 hover:bg-gray-100 cursor-pointer rounded">
          Encuentro #1235
        </div>
      </div>
    </div>
  );
};
