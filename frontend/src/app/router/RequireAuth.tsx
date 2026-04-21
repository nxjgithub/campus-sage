import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../../shared/auth/auth";

interface RequireAuthProps {
  children: JSX.Element;
}

export function RequireAuth({ children }: RequireAuthProps) {
  const location = useLocation();
  const { status, isAuthenticated } = useAuth();

  if (status === "loading") {
    return (
      <div className="route-loading" role="status" aria-live="polite">
        <span className="route-loading__indicator" aria-hidden="true" />
        <span>认证状态加载中</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    const redirect = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${redirect}`} replace />;
  }

  return children;
}
