import React from "react";

// Simple sidebar component (could be extracted later)
function Sidebar() {
  return (
    <div style={{ width: "200px", background: "#f0f0f0", padding: "1rem" }}>
      <p>Sidebar</p>
      {/* ...links and sidebar content... */}
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar />
      <main style={{ flex: 1, padding: "1rem" }}>{children}</main>
    </div>
  );
}
