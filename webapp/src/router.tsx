import { createBrowserRouter, RouteObject, Navigate } from "react-router-dom";
import App from "./App";
import HomePage from "./features/home/HomePage";
import AboutPage from "./pages/AboutPage";
import NotFoundPage from "./pages/NotFoundPage";
import LoginPage from "./features/login/LoginPage";
import RegistroPage from "./features/registro/page"; // Rename later in special routes if needed
import SpecialLayout from "./features/app_layout/SpecialLayout";
import PlantillasPage from "./features/plantillas/PlantillaPage";
import EncuentroPage from "./features/encuentro/EncuentroPage";
import EncuentroDetailPage from "./features/encuentro/EncuentroDetailPage";
import DebugTranscriptionPage from "./features/debugTranscription/DebugTranscriptionPage";
import DebugAudioRecordingPage from "./features/debugAudioRecording/DebugAudioRecordingPage";
import AdminRoute from "./features/admin/AdminRoute";
import AdminAuditPage from "./features/admin/AdminAuditPage";
import AdminUsersPage from "./features/admin/AdminUsersPage";

const routes: RouteObject[] = [
  {
    path: "/",
    element: <App />,
    children: [
      {
        index: true, // This handles the root path
        element: <Navigate to="/encuentro" replace />, // Land on the encounters dashboard
      },
      {
        path: "about",
        element: <AboutPage />,
      },
      {
        path: "login",
        element: <LoginPage />,
      },
      {
        // update path from registro to signup for consistency
        path: "registro",
        element: <RegistroPage />,
      },
      {
        path: "home",
        element: (
          <SpecialLayout>
            <HomePage />
          </SpecialLayout>
        ),
      },
      {
        path: "encuentro",
        element: (
          <SpecialLayout>
            <EncuentroPage />
          </SpecialLayout>
        ),
      },
      {
        path: "encuentro/:id",
        element: (
          <SpecialLayout>
            <EncuentroDetailPage />
          </SpecialLayout>
        ),
      },
      //
      {
        path: "plantillas",
        element: (
          <SpecialLayout>
            <PlantillasPage />
          </SpecialLayout>
        ),
      },
      {
        path: "debug/transcripcion",
        element: (
          <SpecialLayout>
            <DebugTranscriptionPage />
          </SpecialLayout>
        ),
      },
      {
        path: "debug/grabacion",
        element: (
          <SpecialLayout>
            <DebugAudioRecordingPage />
          </SpecialLayout>
        ),
      },
      {
        path: "admin",
        element: <Navigate to="/admin/audit" replace />,
      },
      {
        path: "admin/audit",
        element: (
          <SpecialLayout>
            <AdminRoute requiredCapability="can_view_audit">
              <AdminAuditPage />
            </AdminRoute>
          </SpecialLayout>
        ),
      },
      {
        path: "admin/users",
        element: (
          <SpecialLayout>
            <AdminRoute requiredCapability="can_manage_users">
              <AdminUsersPage />
            </AdminRoute>
          </SpecialLayout>
        ),
      },
      {
        path: "*",
        element: <NotFoundPage />,
      },
    ],
  },
];

const baseUrl = import.meta.env.BASE_URL;
const basename =
  baseUrl === "/" ? undefined : baseUrl.replace(/\/$/, "") || undefined;

const router = createBrowserRouter(
  routes,
  basename ? { basename } : undefined,
);

export default router;
