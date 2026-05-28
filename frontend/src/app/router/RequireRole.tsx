import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../../shared/auth/auth";
import { AppRole, getRoleHomePath } from "../../shared/auth/role";

interface RequireRoleProps {
  allow: AppRole | AppRole[];
  children: JSX.Element;
}

export function RequireRole({ allow, children }: RequireRoleProps) {
  const location = useLocation();
  const { status, isAuthenticated, role } = useAuth();

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
  const allowedRoles = Array.isArray(allow) ? allow : [allow];
  if (!allowedRoles.includes(role)) {
    return <Navigate to={getRoleHomePath(role)} replace />;
  }
  return children;
}
