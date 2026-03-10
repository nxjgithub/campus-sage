import {
  DatabaseOutlined,
  DotChartOutlined,
  FileTextOutlined,
  HistoryOutlined,
  LoginOutlined,
  LogoutOutlined,
  MessageOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  TeamOutlined
} from "@ant-design/icons";
import { Button, Layout, Menu, Space, Tag, Tooltip, Typography } from "antd";
import { ReactNode } from "react";
import { Outlet, useLocation, useMatches, useNavigate } from "react-router-dom";
import { useAuth } from "../../shared/auth/auth";
import { AppRole } from "../../shared/auth/role";
import { PortalSwitch } from "../../shared/components/PortalSwitch";
import {
  NavEntry,
  NavIconKey,
  ROUTE_PRELOADERS,
  resolveNavEntry
} from "../../shared/constants/nav";

const { Content, Sider } = Layout;

interface PortalLayoutProps {
  navItems: NavEntry[];
  panelLabel: string;
  panelDescription: string;
  panelRole: AppRole;
}

const NAV_ICONS: Record<NavIconKey, ReactNode> = {
  kb: <DatabaseOutlined />,
  users: <TeamOutlined />,
  documents: <FileTextOutlined />,
  eval: <DotChartOutlined />,
  monitor: <ReloadOutlined />,
  ask: <MessageOutlined />,
  conversations: <HistoryOutlined />
};

function preloadRoute(path: string) {
  const loader = ROUTE_PRELOADERS[path];
  if (!loader) {
    return;
  }
  void loader();
}

function resolveSelectedKey(pathname: string, navItems: NavEntry[]) {
  const matched = resolveNavEntry(pathname, navItems);
  return matched?.key ?? navItems[0]?.key ?? pathname;
}

function resolveLayoutPreference(matches: ReturnType<typeof useMatches>) {
  const matched = [...matches].reverse().find((item) => {
    const handle = item.handle as { layout?: { hideGlobalSider?: boolean } } | undefined;
    return Boolean(handle?.layout);
  });
  const handle = matched?.handle as { layout?: { hideGlobalSider?: boolean } } | undefined;
  return handle?.layout ?? {};
}

function resolvePortalTone(role: AppRole) {
  return role === "admin" ? "治理视角" : "问答视角";
}

function resolveRoleText(role: AppRole) {
  return role === "admin" ? "管理员" : "用户";
}

export function PortalLayout({
  navItems,
  panelLabel,
  panelDescription,
  panelRole
}: PortalLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const matches = useMatches();
  const { isAuthenticated, role, user, signOut } = useAuth();
  const layoutPreference = resolveLayoutPreference(matches);
  const hideGlobalSider = Boolean(layoutPreference.hideGlobalSider);
  const isAdminRoute = location.pathname.startsWith("/admin");
  const canSwitchPortal = isAuthenticated && role === "admin";
  const nextPath = encodeURIComponent(`${location.pathname}${location.search}`);
  const contentClassName = hideGlobalSider ? "app-content app-content--ask" : "app-content";
  const activeRoute = resolveNavEntry(location.pathname, navItems);
  const activePortal: AppRole = isAdminRoute ? "admin" : "user";
  const routeTitle = activeRoute?.label ?? panelLabel;

  const handlePortalChange = (targetRole: AppRole) => {
    navigate(targetRole === "admin" ? "/admin/kb" : "/app/ask");
  };

  const handleSignOut = async () => {
    await signOut();
    navigate("/app/ask", { replace: true });
  };

  return (
    <Layout className={hideGlobalSider ? "app-shell app-shell--no-sider" : "app-shell"}>
      {!hideGlobalSider ? (
        <Sider width={280} className="app-sider">
          <Tooltip
            placement="rightTop"
            title={
              <Space direction="vertical" size={4}>
                <Typography.Text strong>{panelLabel}</Typography.Text>
                <Typography.Text>{panelDescription}</Typography.Text>
              </Space>
            }
          >
            <div className="brand-block">
              <Space size={8} wrap>
                <Typography.Text className="brand-kicker">{panelLabel}</Typography.Text>
                <Tag bordered={false} color={panelRole === "admin" ? "processing" : "cyan"}>
                  {resolvePortalTone(activePortal)}
                </Tag>
              </Space>
              <Typography.Title level={4} className="brand-title">
                CampusSage
              </Typography.Title>
            </div>
          </Tooltip>

          <Menu
            mode="inline"
            selectedKeys={[resolveSelectedKey(location.pathname, navItems)]}
            items={navItems.map((item) => ({
              key: item.key,
              label: (
                <Tooltip title={item.description} placement="right">
                  <span
                    className="nav-menu-link"
                    onMouseEnter={() => preloadRoute(item.key)}
                    onFocus={() => preloadRoute(item.key)}
                  >
                    <span className="nav-menu-icon">{NAV_ICONS[item.iconKey]}</span>
                    <span className="nav-menu-copy">
                      <span className="nav-menu-label__title">{item.label}</span>
                    </span>
                  </span>
                </Tooltip>
              )
            }))}
            onClick={(item) => {
              navigate(item.key);
            }}
          />

          <div className="menu-footer menu-footer--user">
            <Typography.Text className="menu-footer-value">
              {isAuthenticated ? user?.email ?? "已登录用户" : "匿名访问"}
            </Typography.Text>
            <div className="menu-footer-meta">
              <Tag color={isAuthenticated ? "default" : "warning"} bordered={false}>
                {isAuthenticated ? resolveRoleText(role) : "游客"}
              </Tag>
              <Tooltip title={routeTitle}>
                <span className="menu-footer-icon" aria-hidden="true">
                  <SettingOutlined />
                </span>
              </Tooltip>
            </div>
            <div className="menu-footer-actions">
              {canSwitchPortal ? (
                <PortalSwitch
                  activeRole={activePortal}
                  onChange={handlePortalChange}
                  compact
                  labelsHidden
                />
              ) : null}
              <div className="menu-footer-action-row">
                {!isAuthenticated ? (
                  <Tooltip title="游客模式">
                    <Tag icon={<SafetyCertificateOutlined />} color="default" bordered={false}>
                      游客
                    </Tag>
                  </Tooltip>
                ) : null}
                {isAuthenticated ? (
                  <Tooltip title="退出登录">
                    <Button
                      size="small"
                      shape="circle"
                      icon={<LogoutOutlined />}
                      onClick={() => void handleSignOut()}
                      aria-label="退出登录"
                    />
                  </Tooltip>
                ) : (
                  <Tooltip title="登录">
                    <Button
                      size="small"
                      shape="circle"
                      type="primary"
                      icon={<LoginOutlined />}
                      onClick={() => {
                        navigate(`/login?next=${nextPath}`);
                      }}
                      aria-label="登录"
                    />
                  </Tooltip>
                )}
              </div>
            </div>
          </div>
        </Sider>
      ) : null}
      <Layout>
        <Content className={contentClassName}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
