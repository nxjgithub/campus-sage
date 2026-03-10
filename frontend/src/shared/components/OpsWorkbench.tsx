import { InfoCircleOutlined } from "@ant-design/icons";
import { ReactNode } from "react";
import { Card, Space, Tooltip, Typography } from "antd";

interface OpsWorkbenchProps {
  left: ReactNode;
  right: ReactNode;
}

interface OpsPaneProps {
  title: ReactNode;
  extra?: ReactNode;
  introTitle?: string;
  introDescription?: string;
  toolbar?: ReactNode;
  dense?: boolean;
  children: ReactNode;
}

export function OpsWorkbench({ left, right }: OpsWorkbenchProps) {
  return <div className="ops-workbench">{left}{right}</div>;
}

export function OpsPane({
  title,
  extra,
  introTitle,
  introDescription,
  toolbar,
  dense = false,
  children
}: OpsPaneProps) {
  const introTooltip = introTitle || introDescription ? (
    <Space direction="vertical" size={4}>
      {introTitle ? <Typography.Text strong>{introTitle}</Typography.Text> : null}
      {introDescription ? <Typography.Text>{introDescription}</Typography.Text> : null}
    </Space>
  ) : null;

  return (
    <Card
      title={
        <div className="ops-pane-head">
          <div className="ops-pane-head__title">{title}</div>
          {introTooltip ? (
            <Tooltip title={introTooltip} placement="topRight">
              <span className="ops-pane-head__hint" role="img" aria-label="查看面板说明">
                <InfoCircleOutlined />
              </span>
            </Tooltip>
          ) : null}
        </div>
      }
      extra={extra}
      className={`card-soft ops-pane-card${dense ? " ops-pane-card--dense" : ""}`}
    >
      <div className="ops-pane-body">
        {toolbar ? <div className="ops-pane-toolbar">{toolbar}</div> : null}
        <div className="ops-scroll-pane">{children}</div>
      </div>
    </Card>
  );
}
