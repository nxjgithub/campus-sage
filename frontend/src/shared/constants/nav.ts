export type NavIconKey =
  | "kb"
  | "users"
  | "documents"
  | "eval"
  | "monitor"
  | "ask"
  | "conversations";

export interface NavEntry {
  key: string;
  label: string;
  description: string;
  section: "admin" | "user";
  iconKey: NavIconKey;
}

export const ADMIN_NAV_ITEMS: NavEntry[] = [
  {
    key: "/admin/kb",
    label: "知识库管理",
    description: "维护可见性、检索阈值与上下文预算。",
    section: "admin",
    iconKey: "kb"
  },
  {
    key: "/admin/users",
    label: "用户管理",
    description: "统一管理账号状态、角色与知识库访问权限。",
    section: "admin",
    iconKey: "users"
  },
  {
    key: "/admin/documents",
    label: "文档入库",
    description: "上传多种文件、追踪入库任务并处理失败重试。",
    section: "admin",
    iconKey: "documents"
  },
  {
    key: "/admin/eval",
    label: "评测中心",
    description: "组织评测集、运行离线评测并查看核心指标。",
    section: "admin",
    iconKey: "eval"
  },
  {
    key: "/admin/monitor",
    label: "队列监控",
    description: "查看队列压力、异常任务与系统健康状态。",
    section: "admin",
    iconKey: "monitor"
  }
];

export const USER_NAV_ITEMS: NavEntry[] = [
  {
    key: "/app/ask",
    label: "智能问答",
    description: "围绕指定知识库提问，并查看证据引用与拒答建议。",
    section: "user",
    iconKey: "ask"
  },
  {
    key: "/app/conversations",
    label: "会话记录",
    description: "回看历史问答、引用证据和反馈提交情况。",
    section: "user",
    iconKey: "conversations"
  }
];

export const USER_PUBLIC_NAV_ITEMS: NavEntry[] = [
  {
    key: "/app/ask",
    label: "智能问答",
    description: "匿名模式下也可提问，登录后可保留会话与反馈。",
    section: "user",
    iconKey: "ask"
  }
];

export const ROUTE_PRELOADERS: Record<string, () => Promise<unknown>> = {
  "/admin/kb": async () => import("../../pages/kb/KbPage"),
  "/admin/kb/create": async () => import("../../pages/kb/KbCreatePage"),
  "/admin/users": async () => import("../../pages/users/UsersPage"),
  "/admin/users/create": async () => import("../../pages/users/UsersCreatePage"),
  "/admin/documents": async () => import("../../pages/documents/DocumentsPage"),
  "/admin/documents/upload": async () => import("../../pages/documents/DocumentsUploadPage"),
  "/admin/eval": async () => import("../../pages/eval/EvalPage"),
  "/admin/eval/create": async () => import("../../pages/eval/EvalCreatePage"),
  "/admin/monitor": async () => import("../../pages/monitor/MonitorPage"),
  "/app/ask": async () => import("../../pages/ask/AskPage"),
  "/app/conversations": async () => import("../../pages/conversations/ConversationsPage")
};

export function resolveNavEntry(pathname: string, navItems: NavEntry[]) {
  return navItems.find((item) => pathname.startsWith(item.key)) ?? null;
}
