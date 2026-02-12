import { Space, Typography } from "antd";

interface CopyableFieldProps {
  label: string;
  value?: string | null;
}

export function CopyableField({ label, value }: CopyableFieldProps) {
  if (!value) {
    return (
      <Typography.Text type="secondary">
        {label}: -
      </Typography.Text>
    );
  }

  return (
    <Space size={6} wrap>
      <Typography.Text type="secondary">{label}:</Typography.Text>
      <Typography.Text copyable={{ text: value }}>{value}</Typography.Text>
    </Space>
  );
}
