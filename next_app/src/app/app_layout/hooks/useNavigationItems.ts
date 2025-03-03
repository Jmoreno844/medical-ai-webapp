import { useNuevoEncuentro } from "./useNuevoEncuentro";
import { useEffect } from "react";

type NavigationItem = {
  icon: string;
  label: string;
  path?: string;
  pattern?: string;
  action?: () => void;
  isToggle?: boolean;
  pointerIcon?: string;
};

export const useNavigationItems = (
  toggleEncounters: () => void,
  encountersOpen: boolean
) => {
  const { crearNuevoEncuentro, loading, error } = useNuevoEncuentro();

  // Log any errors that occur during encounter creation
  useEffect(() => {
    if (error) {
      console.error(
        "Error in navigation while creating encounter:",
        error.message
      );
      // Could add a notification system here to show error to user
    }
  }, [error]);

  const navigationItems: NavigationItem[] = [
    { icon: "/home_icon.svg", label: "Home", path: "/home" },
    {
      icon: "/plus.svg",
      label: loading ? "Creando..." : "Crear Encuentro",
      action: crearNuevoEncuentro,
    },
    {
      icon: "/people.svg",
      label: "Últimos Encuentros",
      action: toggleEncounters,
      isToggle: true,
      pattern: "/encuentro",
      pointerIcon: encountersOpen ? "/pointer_left.svg" : "/pointer_right.svg",
    },
    { icon: "/settings.svg", label: "Configuracion", path: "/settings" },
  ];

  return navigationItems;
};
