import { defineConfig } from "vite";

const demoPath = "/magic-english-town/";
const integratedOutput = process.env.WESMARTFLOW_EXAMPLE_OUT_DIR;
const publicPath = process.env.WESMARTFLOW_EXAMPLE_PUBLIC_PATH || demoPath;

export default defineConfig({
  base: publicPath,
  build: integratedOutput
    ? { outDir: integratedOutput, emptyOutDir: true }
    : undefined,
  server: {
    host: "0.0.0.0",
    port: 5188,
    proxy: {
      "/api": {
        target: process.env.MAGIC_TOWN_API_TARGET || "http://127.0.0.1:8080",
        changeOrigin: true,
      },
    },
  },
  plugins: [
    {
      name: "magic-town-root-redirect",
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          if (request.url === "/") {
            response.statusCode = 302;
            response.setHeader("Location", demoPath);
            response.end();
            return;
          }
          next();
        });
      },
    },
  ],
});
