import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => ({
  // Production bundles are served by FastAPI under /app/, so asset URLs need
  // that prefix. The dev server stays at the root for a familiar workflow.
  base: command === "build" ? "/app/" : "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: "dist",
    sourcemap: false
  }
}));