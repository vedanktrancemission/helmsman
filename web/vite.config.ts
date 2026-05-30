import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker, VITE_API_BASE points at the api service; locally it defaults to localhost:8000.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: true },
});
