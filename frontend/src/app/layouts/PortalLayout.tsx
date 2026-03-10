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
  TeamOutlined
} from "@ant-design/icons";
import { Button, Layout, Menu, Space, Tag, Typography } from "antd";
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

const { Header, Content, Sider } = Layout;

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
  const routeDescription = activeRoute?.description ?? panelDescription;

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
        <Sider width={264} className="app-sider">
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
            <Typography.Text className="brand-subtitle">{panelDescription}</Typography.Text>
          </div>

          {canSwitchPortal ? (
            <div className="portal-switch-card">
              <Typography.Text className="portal-switch-card__label">端口切换</Typography.Text>
              <PortalSwitch activeRole={activePortal} onChange={handlePortalChange} compact />
            </div>
          ) : null}

          <div className="nav-section-label">功能导航</div>
          <Menu
            mode="inline"
            selectedKeys={[resolveSelectedKey(location.pathname, navItems)]}
            items={navItems.map((item) => ({
              key: item.key,
              label: (
                <span
                  className="nav-menu-link"
                  onMouseEnter={() => preloadRoute(item.key)}
                  onFocus={() => preloadRoute(item.key)}
                >
                  <span className="nav-menu-icon">{NAV_ICONS[item.iconKey]}</span>
                  <span className="nav-menu-copy">
                    <span className="nav-menu-label__title">{item.label}</span>
                    <span className="nav-menu-label__desc">{item.description}</span>
                  </span>
                </span>
              )
            }))}
            onClick={(item) => {
              navigate(item.key);
            }}
          />

          <div className="menu-footer menu-footer--user">
            <Typography.Text className="menu-footer-key">当前账号</Typography.Text>
            <Typography.Text className="menu-footer-value">
              {isAuthenticated ? user?.email ?? "已登录用户" : "匿名访问"}
            </Typography.Text>
            <Typography.Text className="menu-footer-key">访问角色</Typography.Text>
            <Typography.Text className="menu-footer-value">
              {isAuthenticated ? resolveRoleText(role) : "游客"}
            </Typography.Text>
            <Typography.Text className="menu-footer-key">当前界面</Typography.Text>
            <Typography.Text className="menu-footer-value">{routeTitle}</Typography.Text>
          </div>
        </Sider>
      ) : null}
      <Layout>
        {!hideGlobalSider ? (
          <Header className="app-header app-header--with-tools">
            <div className="header-meta">
              <Typography.Text className="header-eyebrow">{panelLabel}</Typography.Text>
              <Typography.Title level={4} className="header-route-title">
                {routeTitle}
              </Typography.Title>
              <Typography.Text className="header-route-desc">{routeDescription}</Typography.Text>
            </div>
            <div className="app-header-actions">
              <div className="header-user-chip">
                <Typography.Text className="header-user-chip__email">
                  {isAuthenticated ? user?.email ?? "已登录用户" : "匿名访问"}
                </Typography.Text>
                <Tag color={isAuthenticated && role === "admin" ? "processing" : "default"}>
                  {isAuthenticated ? resolveRoleText(role) : "游客"}
                </Tag>
              </div>
              {canSwitchPortal ? (
                <PortalSwitch activeRole={activePortal} onChange={handlePortalChange} />
              ) : null}
              {isAuthenticated ? (
                <Button size="small" icon={<LogoutOutlined />} onClick={() => void handleSignOut()}>
                  退出
                </Button>
              ) : (
                <Space size={8}>
                  <Tag icon={<SafetyCertificateOutlined />} color="default" bordered={false}>
                    匿名模式
                  </Tag>
                  <Button
                    size="small"
                    type="primary"
                    icon={<LoginOutlined />}
                    onClick={() => {
                      navigate(`/login?next=${nextPath}`);
                    }}
                  >
                    登录
                  </Button>
                </Space>
              )}
            </div>
          </Header>
        ) : null}
        <Content className={contentClassName}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
