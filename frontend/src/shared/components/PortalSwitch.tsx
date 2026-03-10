import { AppstoreOutlined, AuditOutlined } from "@ant-design/icons";
import { AppRole } from "../auth/role";

interface PortalSwitchProps {
  activeRole: AppRole;
  onChange: (role: AppRole) => void;
  compact?: boolean;
}

export function PortalSwitch({ activeRole, onChange, compact = false }: PortalSwitchProps) {
  return (
    <div className={compact ? "portal-switch portal-switch--compact" : "portal-switch"}>
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
        <span>用户端</span>
      </button>
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
        <span>管理端</span>
      </button>
    </div>
  );
}
