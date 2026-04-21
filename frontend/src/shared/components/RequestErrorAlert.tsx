import { Alert, Space, Typography } from "antd";
import { ApiErrorShape, resolveApiErrorDisplay } from "../api/errors";

interface RequestErrorAlertProps {
  error: ApiErrorShape;
}

export function RequestErrorAlert({ error }: RequestErrorAlertProps) {
  const display = resolveApiErrorDisplay(error);
  const detail = typeof error.detail === "string" ? error.detail : undefined;

  const description = (
    <Space direction="vertical" size={6} className="request-error-alert__content">
      {display.nextStep ? (
        <Typography.Text className="request-error-alert__next-step">
          {display.nextStep}
        </Typography.Text>
      ) : null}
      {error.message && error.message !== display.summary ? (
        <Typography.Text type="secondary">后端返回：{error.message}</Typography.Text>
      ) : null}
      <div className="request-error-alert__meta">
        {error.request_id ? (
          <Typography.Text type="secondary" copyable={{ text: error.request_id }}>
            请求 ID：{error.request_id}
          </Typography.Text>
        ) : null}
        <Typography.Text type="secondary">错误码：{error.code}</Typography.Text>
      </div>
      {detail ? (
        <Typography.Paragraph className="request-error-alert__detail">
          {detail}
        </Typography.Paragraph>
      ) : null}
    </Space>
  );

  return (
    <Alert
      className="request-error-alert"
      type="error"
      message={display.summary}
      description={description}
      showIcon
    />
  );
}
