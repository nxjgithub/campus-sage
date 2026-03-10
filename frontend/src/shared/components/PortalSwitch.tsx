import { AppstoreOutlined, AuditOutlined } from "@ant-design/icons";
import { Tooltip } from "antd";
import { AppRole } from "../auth/role";

interface PortalSwitchProps {
  activeRole: AppRole;
  onChange: (role: AppRole) => void;
  compact?: boolean;
  labelsHidden?: boolean;
}

export function PortalSwitch({
  activeRole,
  onChange,
  compact = false,
  labelsHidden = false
}: PortalSwitchProps) {
  return (
    <div className={compact ? "portal-switch portal-switch--compact" : "portal-switch"}>
      <Tooltip title="用户端" placement="bottom">
        <button
          type="button"
          className={
            activeRole === "user"
              ? "portal-switch__item portal-switch__item--active"
              : "portal-switch__item"
          }
          aria-label="切换到用户端"
          aria-pressed={activeRole === "user"}
          onClick={() => {
            onChange("user");
          }}
        >
          <AppstoreOutlined />
          {!labelsHidden ? <span>用户端</span> : null}
        </button>
      </Tooltip>
      <Tooltip title="管理端" placement="bottom">
        <button
          type="button"
          className={
            activeRole === "admin"
              ? "portal-switch__item portal-switch__item--active"
              : "portal-switch__item"
          }
          aria-label="切换到管理端"
          aria-pressed={activeRole === "admin"}
          onClick={() => {
            onChange("admin");
          }}
        >
          <AuditOutlined />
          {!labelsHidden ? <span>管理端</span> : null}
        </button>
      </Tooltip>
    </div>
  );
}
