import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

const frontendDir = fileURLToPath(new URL(".", import.meta.url));
const examplesDir = fileURLToPath(new URL("../examples", import.meta.url));

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      "@explore-catalog": fileURLToPath(
        new URL("../examples/explore-catalog.json", import.meta.url),
      ),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    fs: {
      allow: [frontendDir, examplesDir],
    },
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/files": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      // examples demo 的图（dev 模式下由后端 mount 静态目录提供）
      "/court-assets": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
