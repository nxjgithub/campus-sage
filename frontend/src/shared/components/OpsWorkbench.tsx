import { ReactNode } from "react";
import { Card, Typography } from "antd";

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
  return (
    <Card
      title={title}
      extra={extra}
      className={`card-soft ops-pane-card${dense ? " ops-pane-card--dense" : ""}`}
    >
      <div className="ops-pane-body">
        {introTitle || introDescription ? (
          <div className="ops-pane-intro">
            {introTitle ? (
              <Typography.Text className="ops-pane-intro__title">{introTitle}</Typography.Text>
            ) : null}
            {introDescription ? (
              <Typography.Text className="ops-pane-intro__desc">{introDescription}</Typography.Text>
            ) : null}
          </div>
        ) : null}
        {toolbar ? <div className="ops-pane-toolbar">{toolbar}</div> : null}
        <div className="ops-scroll-pane">{children}</div>
      </div>
    </Card>
  );
}
