import { lazy, Suspense } from "react";
import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";
import { useAuth } from "../../shared/auth/auth";
import { getRoleHomePath } from "../../shared/auth/role";
import { RequireAuth } from "./RequireAuth";
import { RequireRole } from "./RequireRole";

const AdminLayout = lazy(async () =>
  import("../layouts/AdminLayout").then((mod) => ({ default: mod.AdminLayout }))
);
const UserLayout = lazy(async () =>
  import("../layouts/UserLayout").then((mod) => ({ default: mod.UserLayout }))
);
const LoginPage = lazy(async () =>
  import("../../pages/auth/LoginPage").then((mod) => ({ default: mod.LoginPage }))
);
const KbPage = lazy(async () =>
  import("../../pages/kb/KbPage").then((mod) => ({ default: mod.KbPage }))
);
const KbCreatePage = lazy(async () =>
  import("../../pages/kb/KbCreatePage").then((mod) => ({ default: mod.KbCreatePage }))
);
const UsersPage = lazy(async () =>
  import("../../pages/users/UsersPage").then((mod) => ({ default: mod.UsersPage }))
);
const UsersCreatePage = lazy(async () =>
  import("../../pages/users/UsersCreatePage").then((mod) => ({ default: mod.UsersCreatePage }))
);
const EvalPage = lazy(async () =>
  import("../../pages/eval/EvalPage").then((mod) => ({ default: mod.EvalPage }))
);
const EvalCreatePage = lazy(async () =>
  import("../../pages/eval/EvalCreatePage").then((mod) => ({ default: mod.EvalCreatePage }))
);
const DocumentsPage = lazy(async () =>
  import("../../pages/documents/DocumentsPage").then((mod) => ({ default: mod.DocumentsPage }))
);
const DocumentsUploadPage = lazy(async () =>
  import("../../pages/documents/DocumentsUploadPage").then((mod) => ({
    default: mod.DocumentsUploadPage
  }))
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

function RouteFallback({ label }: { label: string }) {
  return (
    <div className="route-loading" role="status" aria-live="polite">
      <span className="route-loading__indicator" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

function withSuspense(element: JSX.Element) {
  return <Suspense fallback={<RouteFallback label="页面加载中" />}>{element}</Suspense>;
}

function HomeRedirect() {
  const { status, isAuthenticated, role } = useAuth();
  if (status === "loading") {
    return <RouteFallback label="认证状态加载中" />;
  }
  if (isAuthenticated) {
    return <Navigate to={getRoleHomePath(role)} replace />;
  }
  return <Navigate to="/app/ask" replace />;
}

const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <HomeRedirect />
    },
    {
      path: "/login",
      element: withSuspense(<LoginPage />)
    },
    {
      path: "/app/ask",
      element: withSuspense(<AskPage />)
    },
    {
      path: "/admin",
      element: (
        <RequireRole allow="admin">
          {withSuspense(<AdminLayout />)}
        </RequireRole>
      ),
      children: [
        { index: true, element: <Navigate to="/admin/kb" replace /> },
        { path: "kb", element: withSuspense(<KbPage />) },
        { path: "kb/create", element: withSuspense(<KbCreatePage />) },
        { path: "users", element: withSuspense(<UsersPage />) },
        { path: "users/create", element: withSuspense(<UsersCreatePage />) },
        { path: "documents", element: withSuspense(<DocumentsPage />) },
        { path: "documents/upload", element: withSuspense(<DocumentsUploadPage />) },
        { path: "eval", element: withSuspense(<EvalPage />) },
        { path: "eval/create", element: withSuspense(<EvalCreatePage />) },
        { path: "monitor", element: withSuspense(<MonitorPage />) }
      ]
    },
    {
      path: "/app",
      element: withSuspense(<UserLayout />),
      children: [
        { index: true, element: <Navigate to="/app/ask" replace /> },
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
  ],
  {
    future: {
      v7_relativeSplatPath: true
    }
  }
);

export function AppRouter() {
  return <RouterProvider router={router} future={{ v7_startTransition: true }} />;
}
