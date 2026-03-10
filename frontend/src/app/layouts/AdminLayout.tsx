import { PortalLayout } from "./PortalLayout";
import { ADMIN_NAV_ITEMS } from "../../shared/constants/nav";

export function AdminLayout() {
  return (
    <PortalLayout
      navItems={ADMIN_NAV_ITEMS}
      panelLabel="管理端"
      panelDescription="围绕知识库、文档、账号、评测和监控进行集中治理。"
      panelRole="admin"
    />
  );
}
