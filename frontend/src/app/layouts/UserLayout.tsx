import { PortalLayout } from "./PortalLayout";
import { useAuth } from "../../shared/auth/auth";
import { USER_NAV_ITEMS, USER_PUBLIC_NAV_ITEMS } from "../../shared/constants/nav";

export function UserLayout() {
  const { isAuthenticated } = useAuth();

  return (
    <PortalLayout
      navItems={isAuthenticated ? USER_NAV_ITEMS : USER_PUBLIC_NAV_ITEMS}
      panelLabel="用户端"
      panelDescription="聚焦提问、证据查看与历史会话回看。"
      panelRole="user"
    />
  );
}
