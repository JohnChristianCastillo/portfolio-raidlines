import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The published site lives at the root of raidlines.pages.dev, so assets are
// referenced from "/". It used to build for "/raidlines/" because it was served
// under a path by the gateway; set RAIDLINES_BASE if that ever comes back.
//
// In dev Vite serves at the root anyway and proxies the data API to the local
// backend on :8600.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: loadEnv(mode, process.cwd(), "RAIDLINES_").RAIDLINES_BASE || "/",
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8600",
    },
  },
}));
