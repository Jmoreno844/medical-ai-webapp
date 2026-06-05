import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "@/commons/hooks/useAuth";
import type { AdminCapabilityKey } from "@/api/admin";

type AdminRouteProps = {
  children: ReactNode;
  requiredCapability?: AdminCapabilityKey;
};

export default function AdminRoute({
  children,
  requiredCapability = "can_access_admin_panel",
}: AdminRouteProps) {
  const { capabilities, isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!capabilities[requiredCapability]) {
    return <Navigate to="/home" replace />;
  }

  return <>{children}</>;
}
