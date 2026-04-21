import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function normalizeModuleId(id: string) {
  return id.replace(/\\/g, "/");
}

function resolveAntdChunk(id: string) {
  if (
    id.includes("@ant-design/cssinjs") ||
    id.includes("@ant-design/colors") ||
    id.includes("@ant-design/fast-color") ||
    id.includes("/antd/es/app") ||
    id.includes("/antd/es/config-provider") ||
    id.includes("/antd/es/theme") ||
    id.includes("/antd/es/style") ||
    id.includes("/antd/es/_util") ||
    id.includes("/antd/es/locale") ||
    id.includes("/antd/es/version")
  ) {
    return "vendor-antd-core";
  }
  return undefined;
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8010",
        changeOrigin: true
      }
    }
  },
  build: {
    modulePreload: {
      resolveDependencies(_filename, deps, context) {
        if (context.hostType !== "html") {
          return deps;
        }
        return deps.filter((dep) =>
          [
            "vendor-react",
            "vendor-router",
            "vendor-query",
            "vendor-axios",
            "vendor-antd-core"
          ].some((name) => dep.includes(name))
        );
      }
    },
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = normalizeModuleId(id);
          if (!normalizedId.includes("node_modules")) {
            return undefined;
          }
          if (
            normalizedId.includes("/react/") ||
            normalizedId.includes("/react-dom/") ||
            normalizedId.includes("/scheduler/")
          ) {
            return "vendor-react";
          }
          if (normalizedId.includes("react-router") || normalizedId.includes("@remix-run/router")) {
            return "vendor-router";
          }
          if (normalizedId.includes("@tanstack/react-query")) {
            return "vendor-query";
          }
          if (normalizedId.includes("axios")) {
            return "vendor-axios";
          }
          const antdChunk = resolveAntdChunk(normalizedId);
          if (antdChunk) {
            return antdChunk;
          }
          return undefined;
        }
      }
    }
  }
});
