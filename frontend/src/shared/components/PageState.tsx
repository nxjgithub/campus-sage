import { ExclamationCircleOutlined, InboxOutlined } from "@ant-design/icons";
import { Skeleton, Typography } from "antd";
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
        <div className="page-state__copy">
          <Typography.Text className="page-state__title">当前条件下暂无内容</Typography.Text>
          <Typography.Text className="page-state__desc">
            完成创建、调整筛选或等待任务处理完成后，结果会在这里显示。
          </Typography.Text>
        </div>
        <div className="page-state__tips" aria-label="下一步建议">
          <span className="page-state__tip">检查当前筛选条件</span>
          <span className="page-state__tip">补充数据或新建内容</span>
          <span className="page-state__tip">稍后刷新查看最新状态</span>
        </div>
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
