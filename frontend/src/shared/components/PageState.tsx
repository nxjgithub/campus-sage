import { Empty, Result, Skeleton } from "antd";
import { ReactNode } from "react";

export type PageStatus = "loading" | "success" | "empty" | "error";

interface PageStateProps {
  status: PageStatus;
  errorTitle?: string;
  errorSubTitle?: string;
  children: ReactNode;
}

export function PageState({
  status,
  errorTitle = "请求失败",
  errorSubTitle = "请稍后重试",
  children
}: PageStateProps) {
  if (status === "loading") {
    return <Skeleton active paragraph={{ rows: 6 }} />;
  }
  if (status === "empty") {
    return <Empty description="暂无数据" />;
  }
  if (status === "error") {
    return <Result status="error" title={errorTitle} subTitle={errorSubTitle} />;
  }
  return <>{children}</>;
}
