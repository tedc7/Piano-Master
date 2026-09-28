import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// base "./": the build works from any folder on the piano server (currently /app/)
export default defineConfig({
  base: "./",
  plugins: [svelte()],
  build: { target: "es2020", chunkSizeWarningLimit: 2000 },
  test: { include: ["tests/**/*.test.ts"] },
});
