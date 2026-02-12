import { Alert, Typography } from "antd";
import { ApiErrorShape } from "../api/errors";

interface RequestErrorAlertProps {
  error: ApiErrorShape;
}

export function RequestErrorAlert({ error }: RequestErrorAlertProps) {
  const detail = typeof error.detail === "string" ? error.detail : undefined;
  const description = (
    <div>
      <div>错误码：{error.code}</div>
      {error.request_id ? <div>请求ID：{error.request_id}</div> : null}
      {detail ? <Typography.Paragraph>{detail}</Typography.Paragraph> : null}
    </div>
  );
  return <Alert type="error" message={error.message} description={description} showIcon />;
}
