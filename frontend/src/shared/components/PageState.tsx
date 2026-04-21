import { ExclamationCircleOutlined, InboxOutlined } from "@ant-design/icons";
import { Empty, Skeleton, Typography } from "antd";
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
    return (
      <div className="page-state page-state--loading" role="status" aria-live="polite">
        <div className="page-state__mark page-state__mark--loading" aria-hidden="true">
          <span className="page-state__spinner" />
        </div>
        <div className="page-state__copy">
          <Typography.Text className="page-state__title">正在加载数据</Typography.Text>
          <Typography.Text className="page-state__desc">
            系统正在同步最新状态，请稍候。
          </Typography.Text>
        </div>
        <div className="page-state__skeleton-grid">
          <Skeleton active paragraph={{ rows: 3 }} title={false} />
          <Skeleton active paragraph={{ rows: 3 }} title={false} />
        </div>
      </div>
    );
  }
  if (status === "empty") {
    return (
      <div className="page-state page-state--empty">
        <div className="page-state__mark" aria-hidden="true">
          <InboxOutlined />
        </div>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <span className="page-state__empty-text">
              暂无数据，完成创建或调整筛选后会在这里显示结果。
            </span>
          }
        />
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="page-state page-state--error" role="alert">
        <div className="page-state__mark page-state__mark--error" aria-hidden="true">
          <ExclamationCircleOutlined />
        </div>
        <div className="page-state__copy">
          <Typography.Text className="page-state__title">{errorTitle}</Typography.Text>
          <Typography.Text className="page-state__desc">{errorSubTitle}</Typography.Text>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
