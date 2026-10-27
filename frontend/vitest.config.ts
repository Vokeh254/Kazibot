import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vitest-specific configuration — separate from vite.config.ts to avoid type conflicts
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
