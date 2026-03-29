import { useContext } from "react";
import { AuthContext } from "@/commons/contexts/AuthContext";
import { useSidebar } from "@/commons/contexts/SidebarContext";

const SidebarUser = () => {
  const { userData } = useContext(AuthContext);
  const { isExpanded } = useSidebar();

  // Use first letters of name and last name for avatar placeholder if no image
  const initials = userData
    ? `${userData.name?.charAt(0) || ""}${userData.last_name?.charAt(0) || ""}`
    : "";

  return (
    <div
      className={`flex items-center ${
        isExpanded ? "justify-start px-2" : "justify-center w-full"
      } py-2`}
    >
      <div className="flex-shrink-0">
        <div className="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-semibold">
          {initials}
        </div>
      </div>

      {isExpanded && userData && (
        <div className="ml-2 max-w-[calc(100%-40px)]">
          <p className="text-sm font-medium truncate">
            {userData.name} {userData.last_name}
          </p>
          <p className="text-xs text-gray-500 truncate">{userData.email}</p>
        </div>
      )}
    </div>
  );
};

export default SidebarUser;
