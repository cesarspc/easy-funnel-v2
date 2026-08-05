/** Vite configuration for React + TypeScript SPA. */

import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

function resolveApiBaseUrl(mode: string): string {
  // loadEnv reads both frontend/.env* files and variables injected into the
  // build process by Cloudflare. Reading this explicitly makes production
  // configuration deterministic instead of relying on an implicit fallback.
  const env = loadEnv(mode, process.cwd(), "VITE_");
  // Production must come from the deployment build environment itself. Do not
  // accept a local .env.production fallback: an ignored developer file can
  // otherwise make a local build look valid while Cloudflare receives nothing.
  const configured = (
    mode === "production" ? process.env.VITE_API_BASE_URL : env.VITE_API_BASE_URL
  )?.trim();

  if (!configured) {
    if (mode === "production") {
      throw new Error(
        "Missing VITE_API_BASE_URL. Configure it as a Production build variable " +
          "(for example https://api.example.com/api) and redeploy.",
      );
    }
    return "/api";
  }

  const normalized = configured.replace(/\/+$/, "");

  if (mode === "production") {
    let url: URL;
    try {
      url = new URL(normalized);
    } catch {
      throw new Error(
        `Invalid VITE_API_BASE_URL "${configured}": production requires an absolute HTTPS URL.`,
      );
    }

    if (url.protocol !== "https:") {
      throw new Error(
        `Invalid VITE_API_BASE_URL "${configured}": production requires HTTPS.`,
      );
    }
  }

  return normalized;
}

export default defineConfig(({ mode }) => {
  const apiBaseUrl = resolveApiBaseUrl(mode);

  // This line appears in Cloudflare's build log and proves which URL was
  // compiled into the immutable browser bundle. It contains no secret.
  console.info(`[vite] API base URL: ${apiBaseUrl}`);

  return {
    plugins: [react()],
    base: "/",
    define: {
      __API_BASE_URL__: JSON.stringify(apiBaseUrl),
    },
    build: {
      outDir: "dist",
      sourcemap: false,
      minify: "terser",
      terserOptions: {
        compress: {
          drop_console: true,
        },
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
    resolve: {
      alias: {
        "@": "/src",
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      globals: true,
    },
  };
});
