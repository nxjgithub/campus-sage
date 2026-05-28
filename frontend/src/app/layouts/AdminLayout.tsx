import { PortalLayout } from "./PortalLayout";
import { useAuth } from "../../shared/auth/auth";
import { ADMIN_NAV_ITEMS } from "../../shared/constants/nav";

export function AdminLayout() {
  const { role } = useAuth();
  const navItems =
    role === "admin" ? ADMIN_NAV_ITEMS : ADMIN_NAV_ITEMS.filter((item) => item.key !== "/admin/users");

  return (
    <PortalLayout
      navItems={navItems}
      panelLabel="管理端"
      panelDescription="围绕知识库、文档、账号、评测和监控进行集中治理。"
      panelRole="admin"
    />
  );
}
