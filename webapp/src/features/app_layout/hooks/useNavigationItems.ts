import { useNuevoEncuentro } from "./Encuentros/useNuevoEncuentro";
import { useEffect } from "react";

import { logger } from "@/lib/logger";
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
      logger.error(
        "Error in navigation while creating encounter:",
        error.message
      );
      // Could add a notification system here to show error to user
    }
  }, [error]);

  const navigationItems: NavigationItem[] = [
    { icon: "/home_icon.svg", label: "Inicio", path: "/home" },
    {
      icon: "/plus.svg",
      label: loading ? "Creando…" : "Crear encuentro",
      action: crearNuevoEncuentro,
    },
    {
      icon: "/people.svg",
      label: "Encuentros recientes",
      action: toggleEncounters,
      isToggle: true,
      pattern: "/encuentro",
      pointerIcon: encountersOpen ? "/pointer_left.svg" : "/pointer_right.svg",
    },
    { icon: "/template.svg", label: "Plantillas", path: "/plantillas" },
  ];

  return navigationItems;
};
