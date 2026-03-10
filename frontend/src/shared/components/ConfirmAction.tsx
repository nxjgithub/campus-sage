import { ReactNode } from "react";
import { Button, Popconfirm } from "antd";
import type { ButtonProps } from "antd";

interface ConfirmActionProps {
  title: string;
  description?: string;
  okText?: string;
  cancelText?: string;
  onConfirm: () => void;
  disabled?: boolean;
  buttonText?: string;
  buttonType?: ButtonProps["type"];
  danger?: boolean;
  loading?: boolean;
  size?: ButtonProps["size"];
  shape?: ButtonProps["shape"];
  icon?: ReactNode;
  ariaLabel?: string;
}

export function ConfirmAction({
  title,
  description,
  okText = "确认",
  cancelText = "取消",
  onConfirm,
  disabled,
  buttonText,
  buttonType = "default",
  danger = false,
  loading = false,
  size = "middle",
  shape,
  icon,
  ariaLabel
}: ConfirmActionProps) {
  return (
    <Popconfirm
      title={title}
      description={description}
      okText={okText}
      cancelText={cancelText}
      onConfirm={onConfirm}
      disabled={disabled}
    >
      <Button
        type={buttonType}
        danger={danger}
        loading={loading}
        disabled={disabled}
        size={size}
        shape={shape}
        icon={icon}
        aria-label={ariaLabel}
      >
        {buttonText}
      </Button>
    </Popconfirm>
  );
}
