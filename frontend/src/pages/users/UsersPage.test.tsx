import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchRoleList } from "../../shared/api/modules/roles";
import { createUser, fetchUserList } from "../../shared/api/modules/users";
import { UsersCreatePage } from "./UsersCreatePage";

vi.mock("../../shared/api/modules/users", () => ({
  fetchUserList: vi.fn(),
  createUser: vi.fn()
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
    <MemoryRouter
      initialEntries={["/admin/users/create"]}
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <QueryClientProvider client={queryClient}>
        <AntdApp>{node}</AntdApp>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("UsersCreatePage submit", () => {
  const originalConsoleError = console.error;
  const originalConsoleWarn = console.warn;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      if (args.some((item) => String(item).includes("There may be circular references"))) {
        return;
      }
      originalConsoleError(...args);
    });
    vi.spyOn(console, "warn").mockImplementation((...args: unknown[]) => {
      if (args.some((item) => String(item).includes("There may be circular references"))) {
        return;
      }
      originalConsoleWarn(...args);
    });
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
    vi.mocked(fetchRoleList).mockResolvedValue({
      items: [{ name: "user", permissions: [] }, { name: "admin", permissions: ["*"] }]
    });
    vi.mocked(createUser).mockResolvedValue({
      user_id: "user-2",
      email: "new@example.com",
      status: "active",
      roles: ["user"],
      created_at: "2026-02-12T10:01:00Z",
      updated_at: "2026-02-12T10:01:00Z"
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("should submit expected payload when creating a user", async () => {
    renderWithProviders(<UsersCreatePage />);

    await userEvent.type(screen.getByLabelText("\u90ae\u7bb1"), "new@example.com");
    await userEvent.type(screen.getByLabelText("\u521d\u59cb\u5bc6\u7801"), "User1234");
    await userEvent.click(
      screen.getByRole("button", { name: /\u521b\u5efa\u7528\u6237/ })
    );

    await waitFor(() => {
      expect(createUser).toHaveBeenCalledWith({
        email: "new@example.com",
        password: "User1234",
        roles: ["user"]
      });
    });
  });
});
