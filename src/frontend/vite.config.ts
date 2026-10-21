/// <reference types="vitest/config" />
import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

// PUBLIC_BASE_PATH mirrors the backend's PUBLIC_ROOT_PATH env var (see
// backend/web/handlers.py) so a deployment behind a reverse proxy
// sub-path (e.g. /medicina/) gets correctly prefixed asset and route URLs on
// both sides from the same setting.
const productionBase = process.env.PUBLIC_BASE_PATH ? `${process.env.PUBLIC_BASE_PATH.replace(/\/+$/, "")}/` : "/";

export default defineConfig(({ command, mode }) => {
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
    plugins: [react(), {
      name: "application-text-bootstrap",
      apply: "serve",
      async transformIndexHtml(html) {
        const response = await fetch(new URL(`${base}api/texts`, backend.origin), {
          headers: { "ngrok-skip-browser-warning": "true" },
          signal: AbortSignal.timeout(10000),
        });
        if (!response.ok) throw new Error(`Text catalog HTTP ${response.status}`);
        const texts = await response.json() as Record<string, string>;
        const escapeHtml = (value: string) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
        const replacements: Record<string, string> = {
          __APP_TITLE__: escapeHtml(texts["interface.page_title"]),
          __APP_DESCRIPTION__: escapeHtml(texts["interface.page_description"]),
          __APP_TEXTS__: JSON.stringify(texts).replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029"),
        };
        return html.replace(/__APP_(?:TITLE|DESCRIPTION|TEXTS)__/g, (marker) => replacements[marker]);
      },
      configureServer(server) {
        server.middlewares.use((_request, response, next) => {
          response.setHeader("Cache-Control", "no-store");
          next();
        });
      },
    }],
    define: mode === "test" ? {
      __APP_TEST_TEXTS__: execFileSync(process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3"), ["src/scripts/manage_texts.py", "--public-json"], {
        cwd: fileURLToPath(new URL("../..", import.meta.url)),
        encoding: "utf8",
        env: { ...process.env, PYTHONUTF8: "1", PYTHONPATH: "src" },
      }).trim(),
    } : {},
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
