import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    manifest: true,
    outDir: "../apps/frontend/static/dashboard",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "src/main.ts")
      },
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name][extname]"
      }
    }
  }
});
