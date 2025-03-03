"use client";
import Icon from "@/components/icons/Icon";
import IconButton from "@/components/IconButton";
import { useSidebar } from "@/contexts/SidebarContext";
import { useActivePath } from "@/app/app_layout/hooks/useActivePath";
import { useEncountersSidebar } from "../hooks/Encuentros/useEncountersSidebar";
import { useNavigationItems } from "../hooks/useNavigationItems";
import { EncountersSidebar } from "./EncountersSidebar";
import Link from "next/link";

/**
 * Sidebar component that displays the navigation sidebar with toggle functionality.
 * It handles expand/collapse actions and renders navigation items as well as optional right sidebar.
 *
 * Security note: Ensure that any dynamic data passed into navigation items is properly validated and sanitized.
 */
const Sidebar = () => {
  const { isExpanded, setIsExpanded } = useSidebar();
  const { isActivePath } = useActivePath();
  const { showRightSidebar, toggleSidebar, closeSidebar } =
    useEncountersSidebar();
  const navigationItems = useNavigationItems(toggleSidebar, showRightSidebar);

  /**
   * Handles sidebar click to expand it if currently collapsed.
   */
  const handleSidebarClick = () => {
    if (!isExpanded) {
      setIsExpanded(true);
    }
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
        {/* Logo / top area */}
        <div className="relative flex items-center h-8 md:h-10">
          <div className="flex-grow flex justify-center">
            <Icon
              src="/brand_logo.svg"
              className="h-6 w-6 md:h-7 md:w-7 text-gray-800"
              alt="Brand Logo"
              size={30}
            />
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

        <nav className="mt-2">
          <ul className="space-y-1">
            {navigationItems.map((item, index) => (
              <li
                key={index}
                onClick={(e) => {
                  e.stopPropagation();
                  if (item.isToggle && item.action) {
                    item.action();
                  }
                }}
                className={`flex items-center cursor-pointer h-8 md:h-10 w-10/12 mx-auto ${
                  isActivePath(item.path, item.pattern)
                    ? "bg-blue-600"
                    : "hover:bg-gray-100"
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
                            isActivePath(item.path)
                              ? "filter invert brightness-0 saturate-100"
                              : "text-black"
                          }`}
                          alt={item.label}
                        />
                      </div>
                      {isExpanded && (
                        <span
                          className={`pr-4 text-xs md:text-sm whitespace-nowrap ${
                            isActivePath(item.path)
                              ? "text-white font-medium"
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
                      href={item.path || "#"} // Adding fallback to prevent undefined href
                      className="flex items-center w-full"
                    >
                      <div className="w-10 md:w-12 lg:w-14 flex items-center justify-center">
                        <Icon
                          src={item.icon}
                          className={`h-8 w-4 md:h-5 md:w-5 ${
                            isActivePath(item.path)
                              ? "filter invert brightness-0 saturate-100"
                              : "text-black"
                          }`}
                          alt={item.label}
                        />
                      </div>
                      {isExpanded && (
                        <span
                          className={`pr-4 text-xs md:text-sm whitespace-nowrap ${
                            isActivePath(item.path)
                              ? "text-white font-medium"
                              : "text-black"
                          }`}
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
                          className={`h-8 w-4 md:h-5 md:w-5 ${
                            showRightSidebar
                              ? "filter invert brightness-0 saturate-100"
                              : "text-black"
                          }`}
                          alt={item.label}
                        />
                      </div>
                      {isExpanded && (
                        <div className="flex flex-col leading-none">
                          <span
                            className={`text-xs md:text-sm ${
                              isActivePath(undefined, item.pattern)
                                ? "text-white font-medium"
                                : "text-black"
                            }`}
                          >
                            Últimos
                          </span>
                          <span
                            className={`text-xs md:text-sm ${
                              isActivePath(undefined, item.pattern)
                                ? "text-white font-medium"
                                : "text-black"
                            }`}
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
                          className={`w-3 h-3 md:w-4 md:h-4 ${
                            showRightSidebar
                              ? "filter invert brightness-0 saturate-100"
                              : "text-black"
                          }`}
                        />
                      </div>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </nav>
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
