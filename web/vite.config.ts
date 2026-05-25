import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Dev runs on 5175 so it coexists with the prod statrag-web container
    // (which serves on 5173). See CLAUDE.md + docs/services/chat.md.
    host: true,
    port: 5175,
    proxy: {
      "/api": {
        target: "http://localhost:8766",
        changeOrigin: true,
        // SSE needs no buffering
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            proxyRes.headers["cache-control"] = "no-cache, no-transform";
            proxyRes.headers["x-accel-buffering"] = "no";
          });
        },
      },
    },
  },
});
