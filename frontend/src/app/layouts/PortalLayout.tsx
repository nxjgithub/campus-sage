import { Button, Layout, Menu, Space, Tag, Typography } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../shared/auth/auth";
import { NavEntry, ROUTE_PRELOADERS } from "../../shared/constants/nav";

const { Header, Content, Sider } = Layout;

interface PortalLayoutProps {
  navItems: NavEntry[];
  panelLabel: string;
}

function preloadRoute(path: string) {
  const loader = ROUTE_PRELOADERS[path];
  if (!loader) {
    return;
  }
  void loader();
}

function resolveSelectedKey(pathname: string, navItems: NavEntry[]) {
  const matched = navItems.find((item) => pathname.startsWith(item.key));
  return matched?.key ?? navItems[0]?.key ?? pathname;
}

function nowText() {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date());
}

function currentModule(pathname: string) {
  if (pathname.includes("/admin")) {
    return "管理端";
  }
  return "用户端";
}

export function PortalLayout({ navItems, panelLabel }: PortalLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, role, user, signOut } = useAuth();
  const roleText = role === "admin" ? "管理员" : "用户";
  const nextPath = encodeURIComponent(`${location.pathname}${location.search}`);

  return (
    <Layout className="app-shell">
      <Sider width={228} className="app-sider">
        <div className="brand-block">
          <Typography.Title level={4} className="brand-title">
            CampusSage
          </Typography.Title>
          <Typography.Text className="brand-subtitle">{panelLabel}</Typography.Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[resolveSelectedKey(location.pathname, navItems)]}
          items={navItems.map((item) => ({
            key: item.key,
            label: (
              <span
                onMouseEnter={() => preloadRoute(item.key)}
                onFocus={() => preloadRoute(item.key)}
              >
                {item.label}
              </span>
            )
          }))}
          onClick={(item) => {
            navigate(item.key);
          }}
        />
        <div className="menu-footer">
          <Typography.Text className="menu-footer-key">当前模块</Typography.Text>
          <Typography.Text className="menu-footer-value">
            {currentModule(location.pathname)}
          </Typography.Text>
          <Typography.Text className="menu-footer-key">更新时间</Typography.Text>
          <Typography.Text className="menu-footer-value">{nowText()}</Typography.Text>
        </div>
      </Sider>
      <Layout>
        <Header className="app-header app-header--with-tools">
          <div className="header-meta">
            <Typography.Text className="header-title">
              Evidence-grounded University Knowledge Assistant
            </Typography.Text>
            <Typography.Text className="header-text">
              RAG 检索增强问答平台 · 会话、引用、评测、监控一体化
            </Typography.Text>
          </div>
          {isAuthenticated ? (
            <Space size={8}>
              <Typography.Text>{user?.email}</Typography.Text>
              <Tag color={role === "admin" ? "processing" : "default"}>{roleText}</Tag>
              <Button
                size="small"
                onClick={() => {
                  void signOut().then(() => {
                    navigate("/app/ask", { replace: true });
                  });
                }}
              >
                退出登录
              </Button>
            </Space>
          ) : (
            <Space size={8}>
              <Typography.Text type="secondary">当前为匿名访问</Typography.Text>
              <Button
                size="small"
                type="primary"
                onClick={() => {
                  navigate(`/login?next=${nextPath}`);
                }}
              >
                登录
              </Button>
            </Space>
          )}
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
