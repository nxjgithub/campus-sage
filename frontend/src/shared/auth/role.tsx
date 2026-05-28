export type AppRole = "admin" | "manager" | "user";

export function getRoleHomePath(role: AppRole) {
  return role === "admin" || role === "manager" ? "/admin/kb" : "/app/ask";
}

export function resolveRoleFromRoles(roles?: string[] | null): AppRole {
  if (roles?.includes("admin")) {
    return "admin";
  }
  if (roles?.includes("manager")) {
    return "manager";
  }
  return "user";
}
