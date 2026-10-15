/// <reference types="vitest/config" />
import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

// PUBLIC_BASE_PATH mirrors the backend's PUBLIC_ROOT_PATH env var (see
// backend/web/handlers.py) so a deployment behind a reverse proxy
// sub-path (e.g. /medicina/) gets correctly prefixed asset and route URLs on
// both sides from the same setting.
const productionBase = process.env.PUBLIC_BASE_PATH ? `${process.env.PUBLIC_BASE_PATH.replace(/\/+$/, "")}/` : "/";

export default defineConfig(({ command }) => {
  const backend = new URL(process.env.DEV_BACKEND_URL ?? "https://cristiantone.taila68086.ts.net/medicina/");
  // Keep the backend's mount path locally too, including report links,
  // owner form actions, and scoped cookies returned by production.
  const base = command === "serve" ? `${backend.pathname.replace(/\/+$/, "")}/` : productionBase;
  const backendProxy: ProxyOptions = {
    target: backend.origin,
    changeOrigin: true,
    cookieDomainRewrite: "",
    headers: { "ngrok-skip-browser-warning": "true" },
    configure(proxy) {
      proxy.on("proxyReq", (proxyRequest, request) => {
        // This local server forwards same-origin UI requests to the public
        // backend. Keep its origin checks and owner CSRF validation enabled.
        if (request.headers.origin) proxyRequest.setHeader("Origin", backend.origin);
        if (request.headers.referer) proxyRequest.setHeader("Referer", backend.href);
      });
    },
  };

  return {
    base,
    plugins: [react()],
    server: {
      proxy: {
        [`${base}api/`]: {
          ...backendProxy,
          // api/client.ts is frontend source, not an HTTP API endpoint.
          // Returning its URL leaves it in Vite's transformation pipeline.
          bypass(request) {
            if (request.url && /\.[cm]?[jt]sx?(?:\?|$)/.test(request.url)) return request.url;
          },
        },
        [`${base}healthz`]: backendProxy,
        [`${base}readyz`]: backendProxy,
        [`${base}owner`]: backendProxy,
      },
    },
    build: {
      outDir: "dist",
      sourcemap: true,
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./setupTests.ts"],
    },
  };
});
