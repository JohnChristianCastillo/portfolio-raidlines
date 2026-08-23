import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In production the app is served under the gateway at /raidline, so assets must be
// referenced with that base. In dev it is served at the root by Vite, which proxies
// the data API to the local backend on :8600.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "production" ? "/raidline/" : "/",
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8600",
    },
  },
}));
