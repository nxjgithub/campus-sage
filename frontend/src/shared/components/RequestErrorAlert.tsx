import { Alert, Space, Typography } from "antd";
import { ApiErrorShape } from "../api/errors";

interface RequestErrorAlertProps {
  error: ApiErrorShape;
}

export function RequestErrorAlert({ error }: RequestErrorAlertProps) {
  const detail = typeof error.detail === "string" ? error.detail : undefined;
  const description = (
    <Space direction="vertical" size={4}>
      <Typography.Text>错误码：{error.code}</Typography.Text>
      {error.request_id ? (
        <Typography.Text copyable={{ text: error.request_id }}>
          请求 ID：{error.request_id}
        </Typography.Text>
      ) : null}
      {detail ? <Typography.Paragraph>{detail}</Typography.Paragraph> : null}
    </Space>
  );

  return <Alert type="error" message={error.message} description={description} showIcon />;
}
