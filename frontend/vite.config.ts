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
      // xfwd passes the real client address so the backend can tell LAN clients from
      // loopback ones even through the dev proxy (hot-seat games are loopback-only).
      "/api": { target: backend, changeOrigin: false, xfwd: true },
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true, xfwd: true },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
