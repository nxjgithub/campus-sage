import {
  DatabaseOutlined,
  DotChartOutlined,
  FileTextOutlined,
  HistoryOutlined,
  LoginOutlined,
  LogoutOutlined,
  MenuOutlined,
  MessageOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  TeamOutlined
} from "@ant-design/icons";
import { Button, Drawer, Layout, Menu, Space, Tag, Tooltip, Typography } from "antd";
import { ReactNode, useEffect, useState } from "react";
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

function useIsDesktopLayout() {
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return true;
    }
    return window.matchMedia("(min-width: 901px)").matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mediaQuery = window.matchMedia("(min-width: 901px)");
    const handleChange = (event: MediaQueryListEvent) => {
      setIsDesktop(event.matches);
    };
    setIsDesktop(mediaQuery.matches);
    mediaQuery.addEventListener("change", handleChange);
    return () => {
      mediaQuery.removeEventListener("change", handleChange);
    };
  }, []);

  return isDesktop;
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
  const isDesktop = useIsDesktopLayout();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const layoutPreference = resolveLayoutPreference(matches);
  const hideGlobalSider = Boolean(layoutPreference.hideGlobalSider);
  const isAdminRoute = location.pathname.startsWith("/admin");
  const canSwitchPortal = isAuthenticated && role === "admin";
  const nextPath = encodeURIComponent(`${location.pathname}${location.search}`);
  const contentClassName = hideGlobalSider ? "app-content app-content--ask" : "app-content";
  const activeRoute = resolveNavEntry(location.pathname, navItems);
  const activePortal: AppRole = isAdminRoute ? "admin" : "user";
  const routeTitle = activeRoute?.label ?? panelLabel;
  const desktopSiderWidth = panelRole === "admin" ? 304 : 280;

  const handlePortalChange = (targetRole: AppRole) => {
    setMobileNavOpen(false);
    navigate(targetRole === "admin" ? "/admin/kb" : "/app/ask");
  };

  const handleSignOut = async () => {
    await signOut();
    setMobileNavOpen(false);
    navigate("/app/ask", { replace: true });
  };

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, location.search]);

  const handleNavClick = (targetKey: string) => {
    setMobileNavOpen(false);
    navigate(targetKey);
  };

  const siderContent = (
    <>
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
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden="true">CS</span>
            <div className="brand-copy">
              <Typography.Title level={4} className="brand-title">
                CampusSage
              </Typography.Title>
              <Typography.Text className="brand-description">{panelDescription}</Typography.Text>
            </div>
          </div>
          <div className="brand-overview">
            <div className="brand-overview__item">
              <span className="brand-overview__label">当前视角</span>
              <span className="brand-overview__value">{resolvePortalTone(activePortal)}</span>
            </div>
            <div className="brand-overview__item">
              <span className="brand-overview__label">导航模块</span>
              <span className="brand-overview__value">{navItems.length} 项</span>
            </div>
          </div>
          <Space size={8} wrap className="brand-meta-row">
            <Typography.Text className="brand-kicker">{panelLabel}</Typography.Text>
            <Tag bordered={false} color={panelRole === "admin" ? "processing" : "cyan"}>
              {resolvePortalTone(activePortal)}
            </Tag>
          </Space>
        </div>
      </Tooltip>

      <div className="nav-section-label">工作台</div>
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
                  <span className="nav-menu-label__desc">{item.description}</span>
                </span>
              </span>
            </Tooltip>
          )
        }))}
        onClick={(item) => {
          handleNavClick(item.key);
        }}
      />

      <div className="menu-footer menu-footer--user">
        <Typography.Text className="menu-footer-label">当前身份</Typography.Text>
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
        <Typography.Text className="menu-footer-route">{routeTitle}</Typography.Text>
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
                    setMobileNavOpen(false);
                    navigate(`/login?next=${nextPath}`);
                  }}
                  aria-label="登录"
                />
              </Tooltip>
            )}
          </div>
        </div>
      </div>
    </>
  );

  return (
    <Layout
      className={
        hideGlobalSider
          ? `app-shell app-shell--no-sider${panelRole === "admin" ? " app-shell--admin" : ""}`
          : `app-shell${panelRole === "admin" ? " app-shell--admin" : ""}`
      }
    >
      {!hideGlobalSider && isDesktop ? (
        <Sider
          width={desktopSiderWidth}
          className={panelRole === "admin" ? "app-sider app-sider--admin" : "app-sider"}
        >
          {siderContent}
        </Sider>
      ) : null}
      <Layout>
        {!hideGlobalSider && !isDesktop ? (
          <div className="app-mobile-bar">
            <div className="app-mobile-bar__main">
              <div className="app-mobile-bar__brand">
                <span className="app-mobile-bar__mark" aria-hidden="true">CS</span>
                <div className="app-mobile-bar__copy">
                  <Typography.Text className="app-mobile-bar__title">CampusSage</Typography.Text>
                  <Typography.Text className="app-mobile-bar__route">{routeTitle}</Typography.Text>
                </div>
              </div>
              <Tag bordered={false} color={activePortal === "admin" ? "processing" : "cyan"}>
                {resolvePortalTone(activePortal)}
              </Tag>
            </div>
            <Button
              type="default"
              className="app-mobile-bar__trigger"
              icon={<MenuOutlined />}
              onClick={() => {
                setMobileNavOpen(true);
              }}
              aria-label="打开导航菜单"
            >
              菜单
            </Button>
          </div>
        ) : null}
        <Content className={contentClassName}>
          <Outlet />
        </Content>
      </Layout>
      {!hideGlobalSider && !isDesktop ? (
        <Drawer
          open={mobileNavOpen}
          placement="left"
          width={320}
          closeIcon={null}
          onClose={() => {
            setMobileNavOpen(false);
          }}
          rootClassName="app-mobile-drawer"
        >
          <div
            className={
              panelRole === "admin"
                ? "app-sider app-sider--mobile app-sider--admin"
                : "app-sider app-sider--mobile"
            }
          >
            {siderContent}
          </div>
        </Drawer>
      ) : null}
    </Layout>
  );
}
