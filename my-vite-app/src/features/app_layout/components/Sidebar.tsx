import Icon from "@/commons/components/Icon";
import IconButton from "@/commons/components/IconButton";
import { useSidebar } from "@/commons/contexts/SidebarContext";
import { useEncountersSidebar } from "../hooks/Encuentros/useEncountersSidebar";
import { useNavigationItems } from "../hooks/useNavigationItems";
import { EncountersSidebar } from "./EncountersSidebar";
import { Link } from "react-router-dom";
import SidebarUser from "./SidebarUser";
import { useAuth } from "@/commons/hooks/useAuth";

/**
 * Sidebar component that displays the navigation sidebar with toggle functionality.
 * It handles expand/collapse actions and renders navigation items as well as optional right sidebar.
 *
 * Security note: Ensure that any dynamic data passed into navigation items is properly validated and sanitized.
 */
const Sidebar = () => {
  const { isExpanded, setIsExpanded } = useSidebar();
  const { showRightSidebar, toggleSidebar, closeSidebar } =
    useEncountersSidebar();
  const navigationItems = useNavigationItems(toggleSidebar, showRightSidebar);
  const { logout } = useAuth();

  /**
   * Handles sidebar click to expand it if currently collapsed.
   */
  const handleSidebarClick = () => {
    if (!isExpanded) {
      setIsExpanded(true);
    }
  };

  /**
   * Handles logout action
   */
  const handleLogout = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    await logout();
  };

  return (
    <div className="flex h-screen">
      <div
        onClick={handleSidebarClick}
        className={`bg-white text-black shadow-md z-50 transition-all duration-300 flex flex-col
                    ${
                      isExpanded
                        ? "w-[160px] md:w-[180px] lg:w-[200px]"
                        : "w-10 md:w-12 lg:w-14"
                    }`}
      >
        {/* User info / top area - Replaced logo with SidebarUser */}
        <div className="relative flex items-center h-10 md:h-12">
          <div
            className={`flex-grow overflow-hidden ${isExpanded ? "pr-8" : ""}`}
          >
            <SidebarUser />
          </div>
          {isExpanded && (
            <div className="absolute right-0 pr-2">
              <IconButton
                src="/close_sidebar.svg"
                alt="Close"
                onClick={(e) => {
                  e.stopPropagation();
                  setIsExpanded(false);
                }}
                size={24}
                className="hover:bg-gray-200"
              />
            </div>
          )}
        </div>

        {/* Main navigation section */}
        <nav className="mt-2 flex-grow">
          <ul className="space-y-3 mt-4">
            {navigationItems.map((item, index) => (
              <li
                key={index}
                onClick={(e) => {
                  e.stopPropagation();
                  if (item.isToggle && item.action) {
                    item.action();
                  }
                }}
                className={`flex items-center cursor-pointer h-8 md:h-10 w-10/12 mx-auto rounded-lg  ${
                  item.label === "Crear Encuentro" ||
                  item.label === "Creando..."
                    ? "bg-purple-600 hover:!bg-purple-700"
                    : "hover:bg-gray-100 "
                }`}
              >
                {!item.isToggle ? (
                  item.action ? (
                    // If there's an action, use a button instead of a Link
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        item.action?.();
                      }}
                      className="flex items-center w-full focus:outline-none"
                    >
                      <div className="w-10 md:w-12 lg:w-14 flex items-center justify-center">
                        <Icon
                          src={item.icon}
                          className={`h-8 w-4 md:h-5 md:w-5 ${
                            item.label === "Crear Encuentro" ||
                            item.label === "Creando..."
                              ? "filter invert brightness-0 saturate-100" // Keep white icon for purple button
                              : "text-black"
                          }`}
                          alt={item.label}
                        />
                      </div>
                      {isExpanded && (
                        <span
                          className={`pr-4 text-xs md:text-sm whitespace-nowrap ${
                            item.label === "Crear Encuentro" ||
                            item.label === "Creando..."
                              ? "text-white font-medium" // Keep white text for teal button
                              : "text-black"
                          }`}
                        >
                          {item.label}
                        </span>
                      )}
                    </button>
                  ) : (
                    // If there's a path but no action, use a Link
                    <Link
                      to={item.path || "#"} // Adding fallback to prevent undefined href
                      className="flex items-center w-full"
                    >
                      <div className="w-10 md:w-12 lg:w-14 flex items-center justify-center">
                        <Icon
                          src={item.icon}
                          className={`h-8 w-4 md:h-5 md:w-5 ${"text-black"}`}
                          alt={item.label}
                        />
                      </div>
                      {isExpanded && (
                        <span
                          className={`pr-4 text-xs md:text-sm whitespace-nowrap ${"text-black"}`}
                        >
                          {item.label}
                        </span>
                      )}
                    </Link>
                  )
                ) : (
                  <div className="flex items-center w-full justify-between">
                    <div className="flex items-center">
                      <div className="w-10 md:w-12 lg:w-14 flex items-center justify-center">
                        <Icon
                          src={item.icon}
                          className={`h-8 w-4 md:h-5 md:w-5 ${"text-black"}`}
                          alt={item.label}
                        />
                      </div>
                      {isExpanded && (
                        <div className="flex flex-col leading-none">
                          <span
                            className={`text-xs md:text-sm ${"text-black"}`}
                          >
                            Últimos
                          </span>
                          <span
                            className={`text-xs md:text-sm ${"text-black"}`}
                          >
                            Encuentros
                          </span>
                        </div>
                      )}
                    </div>
                    {isExpanded && item.pointerIcon && (
                      <div className="flex items-center pr-2">
                        <Icon
                          src={item.pointerIcon}
                          alt="Pointer icon"
                          className={`w-3 h-3 md:w-4 md:h-4 ${"text-black"}`}
                        />
                      </div>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </nav>

        {/* Bottom section with settings and logout */}
        <div className="mt-auto border-t border-gray-200">
          {/* Settings button */}
          <div className="w-10/12 mx-auto my-1">
            <Link
              to="/configuracion"
              className="flex items-center w-full py-2 hover:bg-gray-100"
            >
              <div className="w-10 md:w-12 lg:w-14 flex items-center justify-center">
                <Icon
                  src="/settings.svg"
                  className="h-4 w-4 md:h-5 md:w-5 text-black"
                  alt="Configuración"
                />
              </div>
              {isExpanded && (
                <span className="text-xs md:text-sm">Configuración</span>
              )}
            </Link>
          </div>

          {/* Logout button - FIXED */}
          <div className="w-10/12 mx-auto my-1 mb-2">
            <button
              onClick={handleLogout}
              className="flex items-center w-full py-2 hover:bg-gray-100"
            >
              <div className="w-10 md:w-12 lg:w-14 flex items-center justify-center">
                <Icon
                  src="/logout.svg"
                  className="h-4 w-4 md:h-5 md:w-5 text-black"
                  alt="Cerrar Sesión"
                />
              </div>
              {isExpanded && (
                <span className="text-xs md:text-sm">Cerrar Sesión</span>
              )}
            </button>
          </div>

          {/* Removed SidebarUser from here as it's now at the top */}
        </div>
      </div>

      {/* Right Sidebar positioned next to main sidebar */}
      {showRightSidebar && (
        <div className="relative">
          <EncountersSidebar onClose={closeSidebar} />
        </div>
      )}
    </div>
  );
};

export default Sidebar;
