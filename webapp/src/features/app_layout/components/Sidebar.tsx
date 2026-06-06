import Icon from "@/commons/components/Icon";
import IconButton from "@/commons/components/IconButton";
import { useSidebar } from "@/commons/contexts/SidebarContext";
import { useNavigationItems } from "../hooks/useNavigationItems";
import { EncountersSidebar } from "./EncountersSidebar";
import { Link } from "react-router-dom";
import SidebarUser from "./SidebarUser";
import { useAuth } from "@/commons/hooks/useAuth";

interface SidebarProps {
  showRightSidebar: boolean;
  toggleSidebar: () => void;
  closeSidebar: () => void;
}

/**
 * Sidebar component that displays the navigation sidebar with toggle functionality.
 * It handles expand/collapse actions and renders navigation items as well as optional right sidebar.
 *
 * Security note: Ensure that any dynamic data passed into navigation items is properly validated and sanitized.
 */
const Sidebar = ({
  showRightSidebar,
  toggleSidebar,
  closeSidebar,
}: SidebarProps) => {
  const { isExpanded, setIsExpanded } = useSidebar();
  const navigationItems = useNavigationItems(toggleSidebar, showRightSidebar);
  const { logout, capabilities } = useAuth();

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
        className={`bg-white text-black shadow-md z-50 transition-all duration-300 flex flex-col overflow-hidden
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
                alt="Cerrar barra lateral"
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
                className={`flex cursor-pointer w-10/12 mx-auto rounded-lg min-w-0 ${
                  item.isToggle
                    ? "items-center min-h-8 md:min-h-10 h-auto py-1"
                    : "items-center h-8 md:h-10"
                } ${
                  item.icon === "/plus.svg"
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
                      className="flex items-center w-full min-w-0 focus:outline-none"
                    >
                      <div className="w-10 md:w-12 lg:w-14 shrink-0 flex items-center justify-center">
                        <Icon
                          src={item.icon}
                          className={`h-8 w-4 md:h-5 md:w-5 ${
                            item.icon === "/plus.svg"
                              ? "filter invert brightness-0 saturate-100" // Keep white icon for purple button
                              : "text-black"
                          }`}
                          alt={item.label}
                        />
                      </div>
                      {isExpanded && (
                        <span
                          title={item.label}
                          className={`min-w-0 flex-1 truncate pr-2 text-xs md:text-sm ${
                            item.icon === "/plus.svg"
                              ? "text-white font-medium" // Keep white text for purple button
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
                      className="flex items-center w-full min-w-0"
                    >
                      <div className="w-10 md:w-12 lg:w-14 shrink-0 flex items-center justify-center">
                        <Icon
                          src={item.icon}
                          className={`h-8 w-4 md:h-5 md:w-5 ${"text-black"}`}
                          alt={item.label}
                        />
                      </div>
                      {isExpanded && (
                        <span
                          title={item.label}
                          className="min-w-0 flex-1 truncate pr-2 text-xs md:text-sm text-black"
                        >
                          {item.label}
                        </span>
                      )}
                    </Link>
                  )
                ) : (
                  <div className="flex items-center w-full min-w-0 justify-between gap-1">
                    <div className="flex items-center min-w-0 flex-1">
                      <div className="w-10 md:w-12 lg:w-14 shrink-0 self-center flex items-center justify-center">
                        <Icon
                          src={item.icon}
                          className={`h-8 w-4 md:h-5 md:w-5 ${"text-black"}`}
                          alt={item.label}
                        />
                      </div>
                      {isExpanded && (
                        <span className="min-w-0 flex-1 pr-1 text-xs md:text-sm leading-tight text-black">
                          {item.label}
                        </span>
                      )}
                    </div>
                    {isExpanded && item.pointerIcon && (
                      <div className="flex shrink-0 self-center items-center pr-1">
                        <Icon
                          src={item.pointerIcon}
                          alt="Indicador"
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
          {capabilities.can_access_admin_panel && (
            <div className="w-10/12 mx-auto mt-2">
              <Link
                to="/admin"
                className="flex items-center w-full min-w-0 py-2 hover:bg-gray-100 rounded-md"
              >
                <div className="w-10 md:w-12 lg:w-14 shrink-0 flex items-center justify-center">
                  <Icon
                    src="/settings.svg"
                    className="h-4 w-4 md:h-5 md:w-5 text-black"
                    alt="Admin"
                  />
                </div>
                {isExpanded && (
                  <span className="min-w-0 flex-1 truncate text-xs md:text-sm">
                    Admin
                  </span>
                )}
              </Link>
            </div>
          )}

          {/* Logout button - FIXED */}
          <div className="w-10/12 mx-auto my-1 mb-2">
            <button
              onClick={handleLogout}
              className="flex items-center w-full min-w-0 py-2 hover:bg-gray-100"
            >
              <div className="w-10 md:w-12 lg:w-14 shrink-0 flex items-center justify-center">
                <Icon
                  src="/logout.svg"
                  className="h-4 w-4 md:h-5 md:w-5 text-black"
                  alt="Cerrar Sesión"
                />
              </div>
              {isExpanded && (
                <span
                  title="Cerrar sesión"
                  className="min-w-0 flex-1 truncate text-xs md:text-sm"
                >
                  Cerrar sesión
                </span>
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
