export type AppRole = "admin" | "user";

export function getRoleHomePath(role: AppRole) {
  return role === "admin" ? "/admin/kb" : "/app/ask";
}

export function resolveRoleFromRoles(roles?: string[] | null): AppRole {
  if (roles?.includes("admin")) {
    return "admin";
  }
  return "user";
}
