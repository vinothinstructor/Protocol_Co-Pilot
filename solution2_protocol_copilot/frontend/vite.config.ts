import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Convention (mirror Solution 1):
//   Frontend calls /api/<route>
//   Vite proxy strips /api and forwards to backend at http://localhost:8010
//   Backend routes do NOT have an /api prefix
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8010",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/health": {
        target: "http://localhost:8010",
        changeOrigin: true,
      },
      "/protocols": {
        target: "http://localhost:8010",
        changeOrigin: true,
      },
    },
  },
});
