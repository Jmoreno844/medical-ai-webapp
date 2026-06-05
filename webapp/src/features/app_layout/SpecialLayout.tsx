import React from "react";
import { Outlet, Navigate } from "react-router-dom";
import { useAuth } from "@/commons/hooks/useAuth";
import { SidebarProvider, useSidebar } from "@/commons/contexts/SidebarContext";
import Sidebar from "./components/Sidebar";
import { useEncountersSidebar } from "./hooks/Encuentros/useEncountersSidebar";

type SpecialLayoutProps = {
  children?: React.ReactNode;
};

// Inner component that uses sidebar context
const LayoutContent: React.FC<SpecialLayoutProps> = ({ children }) => {
  const { isExpanded } = useSidebar();
  const { showRightSidebar, toggleSidebar, closeSidebar } =
    useEncountersSidebar();

  const mainOffsetClass = showRightSidebar
    ? isExpanded
      ? "ml-[416px] md:ml-[436px] lg:ml-[456px]"
      : "ml-[296px] md:ml-[304px] lg:ml-[312px]"
    : isExpanded
      ? "ml-[160px] md:ml-[180px] lg:ml-[200px]"
      : "ml-10 md:ml-12 lg:ml-14";

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-50">
        <Sidebar
          showRightSidebar={showRightSidebar}
          toggleSidebar={toggleSidebar}
          closeSidebar={closeSidebar}
        />
      </aside>
      <main
        className={`min-w-0 flex-1 overflow-x-hidden transition-all duration-300 ${mainOffsetClass}`}
      >
        {/* Don't render both children and Outlet - choose one based on what's provided */}
        {children || <Outlet />}
      </main>
    </div>
  );
};

const SpecialLayout: React.FC<SpecialLayoutProps> = ({ children }) => {
  const { isAuthenticated } = useAuth();

  // If not authenticated, redirect to login
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <SidebarProvider>
      <LayoutContent children={children} />
    </SidebarProvider>
  );
};

export default SpecialLayout;
