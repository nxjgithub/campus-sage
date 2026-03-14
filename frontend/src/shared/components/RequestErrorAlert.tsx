import { Alert, Space, Typography } from "antd";
import { ApiErrorShape, resolveApiErrorDisplay } from "../api/errors";

interface RequestErrorAlertProps {
  error: ApiErrorShape;
}

export function RequestErrorAlert({ error }: RequestErrorAlertProps) {
  const display = resolveApiErrorDisplay(error);
  const detail = typeof error.detail === "string" ? error.detail : undefined;

  const description = (
    <Space direction="vertical" size={4}>
      {display.nextStep ? <Typography.Text>{display.nextStep}</Typography.Text> : null}
      {error.message && error.message !== display.summary ? (
        <Typography.Text type="secondary">后端返回：{error.message}</Typography.Text>
      ) : null}
      {error.request_id ? (
        <Typography.Text type="secondary" copyable={{ text: error.request_id }}>
          请求 ID：{error.request_id}
        </Typography.Text>
      ) : null}
      <Typography.Text type="secondary">错误码：{error.code}</Typography.Text>
      {detail ? <Typography.Paragraph>{detail}</Typography.Paragraph> : null}
    </Space>
  );

  return <Alert type="error" message={display.summary} description={description} showIcon />;
}
