import { PropsWithChildren } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { queryClient } from "../../shared/api/queryClient";
import { AuthProvider } from "../../shared/auth/auth";

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AntdApp>{children}</AntdApp>
      </AuthProvider>
    </QueryClientProvider>
  );
}
