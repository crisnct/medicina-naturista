/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// PUBLIC_BASE_PATH mirrors the backend's PUBLIC_ROOT_PATH env var (see
// backend/web/handlers.py) so a deployment behind a reverse proxy
// sub-path (e.g. /medicina/) gets correctly prefixed asset and route URLs on
// both sides from the same setting.
const base = process.env.PUBLIC_BASE_PATH ? `${process.env.PUBLIC_BASE_PATH.replace(/\/+$/, "")}/` : "/";

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:7860",
      "/healthz": "http://127.0.0.1:7860",
      "/owner": "http://127.0.0.1:7860",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
  },
});
