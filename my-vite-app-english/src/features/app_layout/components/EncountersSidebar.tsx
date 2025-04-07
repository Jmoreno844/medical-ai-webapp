import IconButton from "@/commons/components/IconButton";
import useEncuentroList from "../hooks/Encuentros/useEncuentroList";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import { useNavigate } from "react-router-dom";

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
  const { encuentros, loading, error } = useEncuentroList();
  const navigate = useNavigate();

  // Format datetime to a more readable format
  const formatDateTime = (dateTimeStr: string) => {
    try {
      return format(new Date(dateTimeStr), "dd MMM yyyy HH:mm", { locale: es });
    } catch {
      return dateTimeStr;
    }
  };

  // Handle navigation to encounter detail page
  const handleEncuentroClick = (encuentroId: number) => {
    navigate(`/encuentro/${encuentroId}`);
    onClose(); // Close the sidebar after navigation
  };

  return (
    <div className="h-screen w-64 bg-white shadow-lg z-40 p-4 flex flex-col">
      <div className="flex justify-between items-center mb-4">
        <h2 className="font-semibold">View Encounters</h2>
        <IconButton
          src="/close_sidebar.svg"
          alt="Close sidebar"
          onClick={onClose}
          size={24}
          className="bg-white"
        />
      </div>

      {loading && (
        <div className="text-center py-4">
          <p>Loading encounters...</p>
        </div>
      )}

      {error && (
        <div className="text-center py-4 text-red-500">
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && encuentros.length === 0 && (
        <div className="text-center py-4 text-gray-500">
          <p>No encounters available</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto pr-1">
        <div className="space-y-2">
          {encuentros.map((encuentro) => (
            <div
              key={encuentro.id}
              className="p-2 hover:bg-gray-100 cursor-pointer rounded border border-gray-200"
              onClick={() => handleEncuentroClick(encuentro.id)}
            >
              <div className="font-medium">
                {encuentro.nombre_encuentro === "Encuentro Nuevo"
                  ? "New Encounter"
                  : encuentro.nombre_encuentro}
              </div>
              <div className="text-sm text-gray-500">
                {formatDateTime(encuentro.fecha)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
