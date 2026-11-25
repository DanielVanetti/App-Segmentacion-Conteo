import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  // Con VITE_USE_MOCKS=false las peticiones a /api van al back end (FastAPI).
  // Con MSW activo, MSW las intercepta antes de llegar aqui.
  server: {
    proxy: {
      "/api": process.env.VITE_PROXY_API ?? "http://127.0.0.1:8000",
    },
  },
})
