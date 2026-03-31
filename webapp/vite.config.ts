import { defineConfig } from "vite";
import path from "path";
import react from "@vitejs/plugin-react-swc";

// https://vite.dev/config/
// GCS website URL is https://storage.googleapis.com/<bucket>/index.html — base must include /bucket/
export default defineConfig({
  base: process.env.VITE_BASE_URL || "/",
  plugins: [react()],
  server: {
    proxy: {
      "/otel/v1/traces": {
        target: "http://127.0.0.1:4318",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/otel/, ""),
      },
    },
  },
  esbuild: {
    drop:
      process.env.NODE_ENV === "production" ? ["console", "debugger"] : [],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
