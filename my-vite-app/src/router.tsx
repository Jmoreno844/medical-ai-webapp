import { createBrowserRouter, RouteObject } from "react-router-dom";
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

const routes: RouteObject[] = [
  {
    path: "/",
    element: <App />,
    children: [
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
        path: "*",
        element: <NotFoundPage />,
      },
    ],
  },
];

const router = createBrowserRouter(routes);

export default router;
