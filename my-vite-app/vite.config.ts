import { defineConfig } from "vite";
import path from "path";
import react from "@vitejs/plugin-react-swc";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    ...(process.env.NODE_ENV === "production"
      ? {
          "console.log": "function(){return;}",
          "console.debug": "function(){return;}",
          "console.error": "function(){return;}",
        }
      : {}),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
