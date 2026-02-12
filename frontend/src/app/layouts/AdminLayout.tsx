import { PortalLayout } from "./PortalLayout";
import { ADMIN_NAV_ITEMS } from "../../shared/constants/nav";

export function AdminLayout() {
  return <PortalLayout navItems={ADMIN_NAV_ITEMS} panelLabel="管理员端" />;
}
