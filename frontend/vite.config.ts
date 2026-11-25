import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const backend = process.env.FYODOR_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  // older browsers too: an offline computer keeps whatever Edge or Chrome it had when it went offline
  build: { target: ["es2020", "edge88", "chrome88", "firefox78", "safari14"] },
  optimizeDeps: { include: ["react", "react-dom", "react-dom/client", "zustand"] },
  server: {
    host: process.env.FYODOR_FRONTEND_HOST ?? "127.0.0.1",
    port: 5173,
    proxy: {
      // xfwd adds X-Forwarded-For, which the backend believes only from a trusted proxy: scripts/dev.sh starts it with
      // FYODOR_TRUSTED_PROXIES=127.0.0.1 (and FYODOR_DEV_TOOLS=1, which trusts this page's :5173 origin), or every dev client is 127.0.0.1 to the guess limits and socket caps.
      // Host authority is the fyodor_host cookie: on :5173 the page gets it only when opened with the launcher's #host=<secret>
      // pasted onto the address (the launcher opens :8000); without it the dev page is a guest.
      "/api": { target: backend, changeOrigin: false, xfwd: true },
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true, xfwd: true },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
