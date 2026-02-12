import { lazy, Suspense } from "react";
import { Spin } from "antd";
import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";
import { useAuth } from "../../shared/auth/auth";
import { getRoleHomePath } from "../../shared/auth/role";
import { AdminLayout } from "../layouts/AdminLayout";
import { UserLayout } from "../layouts/UserLayout";
import { RequireAuth } from "./RequireAuth";
import { RequireRole } from "./RequireRole";
import { LoginPage } from "../../pages/auth/LoginPage";

const KbPage = lazy(async () =>
  import("../../pages/kb/KbPage").then((mod) => ({ default: mod.KbPage }))
);
const UsersPage = lazy(async () =>
  import("../../pages/users/UsersPage").then((mod) => ({ default: mod.UsersPage }))
);
const EvalPage = lazy(async () =>
  import("../../pages/eval/EvalPage").then((mod) => ({ default: mod.EvalPage }))
);
const DocumentsPage = lazy(async () =>
  import("../../pages/documents/DocumentsPage").then((mod) => ({ default: mod.DocumentsPage }))
);
const AskPage = lazy(async () =>
  import("../../pages/ask/AskPage").then((mod) => ({ default: mod.AskPage }))
);
const ConversationsPage = lazy(async () =>
  import("../../pages/conversations/ConversationsPage").then((mod) => ({
    default: mod.ConversationsPage
  }))
);
const MonitorPage = lazy(async () =>
  import("../../pages/monitor/MonitorPage").then((mod) => ({ default: mod.MonitorPage }))
);

function withSuspense(element: JSX.Element) {
  return (
    <Suspense
      fallback={
        <div style={{ display: "grid", placeItems: "center", minHeight: 260 }}>
          <Spin size="large" tip="页面加载中" />
        </div>
      }
    >
      {element}
    </Suspense>
  );
}

function HomeRedirect() {
  const { status, isAuthenticated, role } = useAuth();
  if (status === "loading") {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: 260 }}>
        <Spin size="large" tip="认证状态加载中" />
      </div>
    );
  }
  if (isAuthenticated) {
    return <Navigate to={getRoleHomePath(role)} replace />;
  }
  return <Navigate to="/app/ask" replace />;
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <HomeRedirect />
  },
  {
    path: "/login",
    element: <LoginPage />
  },
  {
    path: "/admin",
    element: (
      <RequireRole allow="admin">
        <AdminLayout />
      </RequireRole>
    ),
    children: [
      { index: true, element: <Navigate to="/admin/kb" replace /> },
      { path: "kb", element: withSuspense(<KbPage />) },
      { path: "users", element: withSuspense(<UsersPage />) },
      { path: "documents", element: withSuspense(<DocumentsPage />) },
      { path: "eval", element: withSuspense(<EvalPage />) },
      { path: "monitor", element: withSuspense(<MonitorPage />) }
    ]
  },
  {
    path: "/app",
    element: <UserLayout />,
    children: [
      { index: true, element: <Navigate to="/app/ask" replace /> },
      { path: "ask", element: withSuspense(<AskPage />) },
      {
        path: "conversations",
        element: (
          <RequireAuth>
            {withSuspense(<ConversationsPage />)}
          </RequireAuth>
        )
      }
    ]
  },
  {
    path: "*",
    element: <Navigate to="/" replace />
  }
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
