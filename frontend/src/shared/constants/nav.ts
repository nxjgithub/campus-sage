export interface NavEntry {
  key: string;
  label: string;
}

export const ADMIN_NAV_ITEMS: NavEntry[] = [
  { key: "/admin/kb", label: "知识库管理" },
  { key: "/admin/users", label: "用户管理" },
  { key: "/admin/documents", label: "文档与入库" },
  { key: "/admin/eval", label: "评测中心" },
  { key: "/admin/monitor", label: "队列监控" }
];

export const USER_NAV_ITEMS: NavEntry[] = [
  { key: "/app/ask", label: "聊天问答" },
  { key: "/app/conversations", label: "会话审计" }
];

export const USER_PUBLIC_NAV_ITEMS: NavEntry[] = [{ key: "/app/ask", label: "聊天问答" }];

export const ROUTE_PRELOADERS: Record<string, () => Promise<unknown>> = {
  "/admin/kb": async () => import("../../pages/kb/KbPage"),
  "/admin/users": async () => import("../../pages/users/UsersPage"),
  "/admin/documents": async () => import("../../pages/documents/DocumentsPage"),
  "/admin/eval": async () => import("../../pages/eval/EvalPage"),
  "/admin/monitor": async () => import("../../pages/monitor/MonitorPage"),
  "/app/ask": async () => import("../../pages/ask/AskPage"),
  "/app/conversations": async () => import("../../pages/conversations/ConversationsPage")
};
