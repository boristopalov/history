import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const api = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/history/server/static", emptyOutDir: true, chunkSizeWarningLimit: 1500 },
  server: {
    proxy: { "/days": api, "/timeline": api, "/query": api, "/agent": api },
  },
  test: { environment: "node" },
});
