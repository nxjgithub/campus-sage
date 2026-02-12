import { describe, expect, it } from "vitest";
import { getRoleHomePath, resolveRoleFromRoles } from "./role";

describe("role helper", () => {
  it("应在包含 admin 角色时返回管理员", () => {
    expect(resolveRoleFromRoles(["user", "admin"])).toBe("admin");
  });

  it("普通用户与匿名默认返回用户角色", () => {
    expect(resolveRoleFromRoles(["user"])).toBe("user");
    expect(resolveRoleFromRoles([])).toBe("user");
    expect(resolveRoleFromRoles(undefined)).toBe("user");
  });

  it("应返回正确首页路由", () => {
    expect(getRoleHomePath("admin")).toBe("/admin/kb");
    expect(getRoleHomePath("user")).toBe("/app/ask");
  });
});
