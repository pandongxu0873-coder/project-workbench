import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Preserve the browser's Host so the API's strict same-origin check remains valid.
      "/api": { target: "http://127.0.0.1:8766", changeOrigin: false },
    },
  },
});
