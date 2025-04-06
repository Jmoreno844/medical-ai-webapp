import { useState } from "react";

export const useEncountersSidebar = () => {
  const [showRightSidebar, setShowRightSidebar] = useState(false);

  const toggleSidebar = () => setShowRightSidebar(!showRightSidebar);
  const closeSidebar = () => setShowRightSidebar(false);

  return {
    showRightSidebar,
    toggleSidebar,
    closeSidebar,
  };
};
