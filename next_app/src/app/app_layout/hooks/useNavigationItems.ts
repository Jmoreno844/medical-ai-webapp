type NavigationItem = {
  icon: string;
  label: string;
  path?: string;
  pattern?: string;
  action?: () => void;
  isToggle?: boolean;
  pointerIcon?: string; // New optional property
};

export const useNavigationItems = (
  toggleEncounters: () => void,
  encountersOpen: boolean // New parameter
) => {
  const navigationItems: NavigationItem[] = [
    { icon: "/home_icon.svg", label: "Home", path: "/home" },
    {
      icon: "/plus.svg",
      label: "Crear Encuentro",
      path: "/encuentro/new", // Changed from "/encuentro" to "/encuentro/new"
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
