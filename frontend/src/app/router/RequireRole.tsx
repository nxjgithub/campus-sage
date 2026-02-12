import { Navigate } from "react-router-dom";
import { useAuth } from "../../shared/auth/auth";
import { AppRole, getRoleHomePath } from "../../shared/auth/role";

interface RequireRoleProps {
  allow: AppRole;
  children: JSX.Element;
}

export function RequireRole({ allow, children }: RequireRoleProps) {
  const { isAuthenticated, role } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (role !== allow) {
    return <Navigate to={getRoleHomePath(role)} replace />;
  }
  return children;
}
