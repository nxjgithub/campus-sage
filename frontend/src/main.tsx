import React from "react";
import ReactDOM from "react-dom/client";
import ConfigProvider from "antd/es/config-provider";
import { AppProviders } from "./app/providers/AppProviders";
import { AppRouter } from "./app/router";
import "./shared/styles/tokens.css";
import "./shared/styles/global.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("未找到根节点 #root");
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#0f5bd8",
          colorSuccess: "#1f9d55",
          colorWarning: "#e5a100",
          colorError: "#cf3f3f",
          borderRadius: 12,
          fontFamily: '"Source Han Sans SC", "Noto Sans SC", "PingFang SC", sans-serif'
        }
      }}
    >
      <AppProviders>
        <AppRouter />
      </AppProviders>
    </ConfigProvider>
  </React.StrictMode>
);
