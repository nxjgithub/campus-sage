import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchKbList } from "../../shared/api/modules/kb";
import { fetchRoleList } from "../../shared/api/modules/roles";
import {
  createUser,
  deleteUserKbAccess,
  fetchUserKbAccess,
  fetchUserList,
  replaceUserKbAccess,
  updateUser,
  upsertUserKbAccess
} from "../../shared/api/modules/users";
import { UsersPage } from "./UsersPage";

vi.mock("../../shared/api/modules/users", () => ({
  fetchUserList: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  fetchUserKbAccess: vi.fn(),
  upsertUserKbAccess: vi.fn(),
  deleteUserKbAccess: vi.fn(),
  replaceUserKbAccess: vi.fn()
}));

vi.mock("../../shared/api/modules/kb", () => ({
  fetchKbList: vi.fn()
}));

vi.mock("../../shared/api/modules/roles", () => ({
  fetchRoleList: vi.fn()
}));

function renderWithProviders(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <AntdApp>{node}</AntdApp>
    </QueryClientProvider>
  );
}

describe("UsersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchUserList).mockResolvedValue({
      items: [
        {
          user_id: "user-1",
          email: "user1@example.com",
          status: "active",
          roles: ["user"],
          created_at: "2026-02-12T10:00:00Z"
        }
      ],
      total: 1,
      limit: 20,
      offset: 0
    });
    vi.mocked(createUser).mockResolvedValue({
      user_id: "user-2",
      email: "new@example.com",
      status: "active",
      roles: ["user"],
      created_at: "2026-02-12T10:01:00Z",
      updated_at: "2026-02-12T10:01:00Z"
    });
    vi.mocked(updateUser).mockResolvedValue({
      user_id: "user-1",
      email: "user1@example.com",
      status: "disabled",
      roles: ["user"],
      created_at: "2026-02-12T10:00:00Z",
      updated_at: "2026-02-12T10:02:00Z"
    });
    vi.mocked(fetchUserKbAccess).mockResolvedValue({
      user_id: "user-1",
      items: []
    });
    vi.mocked(upsertUserKbAccess).mockResolvedValue({
      user_id: "user-1",
      items: [{ kb_id: "kb-1", access_level: "read" }]
    });
    vi.mocked(deleteUserKbAccess).mockResolvedValue({
      user_id: "user-1",
      kb_id: "kb-1",
      status: "deleted"
    });
    vi.mocked(replaceUserKbAccess).mockResolvedValue({
      user_id: "user-1",
      items: [{ kb_id: "kb-1", access_level: "read" }]
    });
    vi.mocked(fetchRoleList).mockResolvedValue({
      items: [{ name: "user", permissions: [] }, { name: "admin", permissions: ["*"] }]
    });
    vi.mocked(fetchKbList).mockResolvedValue({ items: [] });
  });

  it("创建用户时应提交正确 payload", async () => {
    renderWithProviders(<UsersPage />);

    await userEvent.type(screen.getByLabelText("邮箱"), "new@example.com");
    await userEvent.type(screen.getByLabelText("初始密码"), "User1234");
    await userEvent.click(screen.getByRole("button", { name: /创建用户/ }));

    await waitFor(() => {
      expect(createUser).toHaveBeenCalledWith({
        email: "new@example.com",
        password: "User1234",
        roles: ["user"]
      });
    });
  });
});
