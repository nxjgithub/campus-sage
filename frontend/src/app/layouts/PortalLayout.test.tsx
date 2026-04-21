import { ReactNode } from "react";
import { App as AntdApp } from "antd";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { AdminLayout } from "./AdminLayout";
import { UserLayout } from "./UserLayout";
import { AppRole } from "../../shared/auth/role";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate
  };
});

interface MockAuthState {
  status: "loading" | "authenticated" | "anonymous";
  role: AppRole;
  isAuthenticated: boolean;
  user: { email: string; roles?: string[] } | null;
  signOut: ReturnType<typeof vi.fn>;
  signIn: ReturnType<typeof vi.fn>;
  refreshUser: ReturnType<typeof vi.fn>;
}

const mockAuthState: MockAuthState = {
  status: "anonymous",
  role: "user",
  isAuthenticated: false,
  user: null,
  signOut: vi.fn().mockResolvedValue(undefined),
  signIn: vi.fn().mockResolvedValue(undefined),
  refreshUser: vi.fn().mockResolvedValue(undefined)
};

vi.mock("../../shared/auth/auth", () => ({
  useAuth: () => mockAuthState
}));

function renderWithRouter(initialEntries: string[], routes: Parameters<typeof createMemoryRouter>[0]) {
  const router = createMemoryRouter(routes, {
    initialEntries,
    future: { v7_relativeSplatPath: true }
  });
  return render(
    <AntdApp>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </AntdApp>
  );
}

function createUserLayoutRoutes(extraChildren?: ReactNode, hideSider = false) {
  return [
    {
      path: "/app",
      element: <UserLayout />,
      children: [
        {
          path: "demo",
          element: extraChildren ?? <div>用户演示页</div>
        },
        {
          path: "ask",
          handle: hideSider ? { layout: { hideGlobalSider: true } } : undefined,
          element: <div>问答页</div>
        }
      ]
    }
  ];
}

function createAdminAndUserRoutes() {
  return [
    {
      path: "/admin",
      element: <AdminLayout />,
      children: [
        { path: "kb", element: <div>知识库页</div> },
        { path: "users", element: <div>用户页</div> }
      ]
    },
    {
      path: "/app",
      element: <UserLayout />,
      children: [{ path: "ask", element: <div>问答页</div> }]
    }
  ];
}

describe("PortalLayout", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    mockAuthState.status = "anonymous";
    mockAuthState.role = "user";
    mockAuthState.isAuthenticated = false;
    mockAuthState.user = null;
    mockAuthState.signOut = vi.fn().mockResolvedValue(undefined);
    mockAuthState.signIn = vi.fn().mockResolvedValue(undefined);
    mockAuthState.refreshUser = vi.fn().mockResolvedValue(undefined);
  });

  it("匿名态在常规用户路由显示登录入口", async () => {
    renderWithRouter(["/app/demo"], createUserLayoutRoutes());

    expect(await screen.findByText("用户演示页")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /登录/ })).toBeInTheDocument();
    expect(screen.getByText("匿名访问")).toBeInTheDocument();
    expect(screen.queryByLabelText("切换到管理端")).not.toBeInTheDocument();
  });

  it("登录管理员可切换到用户端", async () => {
    mockAuthState.status = "authenticated";
    mockAuthState.role = "admin";
    mockAuthState.isAuthenticated = true;
    mockAuthState.user = { email: "admin@example.com", roles: ["admin"] };

    renderWithRouter(["/admin/users"], createAdminAndUserRoutes());

    expect(await screen.findByText("用户页")).toBeInTheDocument();
    expect(screen.getByText("admin@example.com")).toBeInTheDocument();

    await userEvent.click(screen.getAllByLabelText("切换到用户端")[0]);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/app/ask");
    });
  });

  it("根据当前路由高亮对应导航项", async () => {
    mockAuthState.status = "authenticated";
    mockAuthState.role = "admin";
    mockAuthState.isAuthenticated = true;
    mockAuthState.user = { email: "admin@example.com", roles: ["admin"] };

    renderWithRouter(["/admin/users"], createAdminAndUserRoutes());

    await screen.findByText("用户页");
    const selectedItem = document.querySelector(".ant-menu-item-selected");
    if (!(selectedItem instanceof HTMLElement)) {
      throw new Error("未找到选中的导航项");
    }
    expect(within(selectedItem).getByText("用户管理")).toBeInTheDocument();
  });

  it("通过路由元信息隐藏问答页全局侧栏", async () => {
    renderWithRouter(["/app/ask"], createUserLayoutRoutes(undefined, true));

    expect(await screen.findByText("问答页")).toBeInTheDocument();
    expect(document.querySelector(".app-sider")).not.toBeInTheDocument();
    expect(document.querySelector(".app-header")).not.toBeInTheDocument();
  });
});
