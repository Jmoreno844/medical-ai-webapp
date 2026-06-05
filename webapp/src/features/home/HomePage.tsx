import { Navigate } from "react-router-dom";

// The post-login landing is the encounters dashboard at /encuentro.
// /home is kept as a redirect so existing navigate("/home") calls keep working.
export default function HomePage() {
  return <Navigate to="/encuentro" replace />;
}
