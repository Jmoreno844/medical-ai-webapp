import React from "react";
import { Outlet, Navigate } from "react-router-dom";
import { useAuth } from "@/commons/hooks/useAuth";
import { SidebarProvider, useSidebar } from "@/commons/contexts/SidebarContext";
import Sidebar from "./components/Sidebar";

type SpecialLayoutProps = {
  children?: React.ReactNode;
};

// Inner component that uses sidebar context
const LayoutContent: React.FC<SpecialLayoutProps> = ({ children }) => {
  const { isExpanded } = useSidebar();

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-50">
        <Sidebar />
      </aside>
      <main
        className={`min-w-0 flex-1 overflow-x-hidden transition-all duration-300 ${
          isExpanded ? "ml-[200px] lg:ml-[224px]" : "ml-12 lg:ml-14"
        }`}
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
