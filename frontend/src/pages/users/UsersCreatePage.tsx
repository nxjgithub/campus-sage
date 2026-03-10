import { ArrowLeftOutlined, PlusOutlined, UserAddOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, Select, Space, Typography, message } from "antd";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { fetchRoleList } from "../../shared/api/modules/roles";
import { createUser, fetchUserList } from "../../shared/api/modules/users";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";

interface CreateUserValues {
  email: string;
  password: string;
  roles: string[];
}

export function UsersCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<CreateUserValues>();

  const usersQuery = useQuery({
    queryKey: ["users", "create-page", "summary"],
    queryFn: async () => fetchUserList({ limit: 1, offset: 0 })
  });

  const activeUsersQuery = useQuery({
    queryKey: ["users", "create-page", "summary", "active"],
    queryFn: async () => fetchUserList({ status: "active", limit: 1, offset: 0 })
  });

  const roleQuery = useQuery({
    queryKey: ["roles", "list"],
    queryFn: fetchRoleList
  });

  const roleOptions = useMemo(() => {
    if (roleQuery.data?.items?.length) {
      return roleQuery.data.items.map((item) => ({
        value: item.name,
        label: item.name
      }));
    }
    return [
      { value: "user", label: "user" },
      { value: "admin", label: "admin" }
    ];
  }, [roleQuery.data?.items]);

  const createMutation = useMutation({
    mutationFn: async (values: CreateUserValues) =>
      createUser({
        email: values.email.trim(),
        password: values.password,
        roles: values.roles
      }),
    onSuccess: async () => {
      message.success("用户创建成功");
      form.resetFields();
      form.setFieldValue("roles", ["user"]);
      await queryClient.invalidateQueries({ queryKey: ["users", "list"] });
      navigate("/admin/users");
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const watchedEmail = Form.useWatch("email", form) ?? "";
  const watchedPassword = Form.useWatch("password", form) ?? "";
  const watchedRoles = Form.useWatch("roles", form) ?? ["user"];

  return (
    <div className="page-stack">
      {createMutation.isError ? (
        <RequestErrorAlert error={normalizeApiError(createMutation.error)} />
      ) : null}

      <Card className="card-soft split-overview-card">
        <div className="split-overview">
          <div className="split-overview__copy">
            <div className="split-overview__label-row">
              <span className="hero-kicker">用户创建</span>
              <Typography.Text className="split-overview__eyebrow">
                把新增账号与后续授权拆开，创建页只聚焦基础录入和初始角色。
              </Typography.Text>
            </div>
            <Typography.Title level={3} className="hero-title">
              新建用户账号
            </Typography.Title>
            <Typography.Paragraph className="split-overview__desc">
              左侧录入邮箱、密码和角色，右侧同步展示账号摘要与后续操作建议，让页面既不空，也不拥挤。
            </Typography.Paragraph>
            <div className="split-overview__notes">
              <span className="split-overview__note">默认从最小权限角色开始</span>
              <span className="split-overview__note">复杂授权回到列表页继续处理</span>
            </div>
          </div>
          <div className="split-overview__stats">
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">账号总数</span>
              <span className="split-overview-stat__value">{usersQuery.data?.total ?? 0}</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">活跃账号</span>
              <span className="split-overview-stat__value">{activeUsersQuery.data?.total ?? 0}</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">角色类型</span>
              <span className="split-overview-stat__value">{roleOptions.length}</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">默认角色</span>
              <span className="split-overview-stat__value">user</span>
            </div>
          </div>
        </div>
      </Card>

      <Card
        className="card-soft split-action-card"
        title={
          <Space size={8}>
            <UserAddOutlined />
            <span>填写账号信息</span>
          </Space>
        }
        extra={
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => {
              navigate("/admin/users");
            }}
          >
            返回列表
          </Button>
        }
      >
        <div className="split-action-card__body split-action-card__body--full">
          <div className="split-create-layout">
            <div className="split-create-main">
              <div className="split-pane-copy">
                <Typography.Text className="split-pane-copy__title">先完成账号开通</Typography.Text>
                <Typography.Text className="split-pane-copy__desc">
                  创建页只保留账号录入所需的最小字段，避免把状态调整、知识库授权和列表治理堆在同一屏。
                </Typography.Text>
              </div>

              <Form<CreateUserValues>
                form={form}
                layout="vertical"
                initialValues={{ roles: ["user"] }}
                onFinish={(values) => {
                  createMutation.mutate(values);
                }}
              >
                <Form.Item
                  name="email"
                  label="邮箱"
                  rules={[
                    { required: true, message: "请输入邮箱" },
                    { type: "email", message: "邮箱格式不正确" }
                  ]}
                >
                  <Input placeholder="user@example.com" />
                </Form.Item>
                <Form.Item
                  name="password"
                  label="初始密码"
                  rules={[{ required: true, message: "请输入初始密码" }]}
                >
                  <Input.Password placeholder="建议包含字母和数字" />
                </Form.Item>
                <Form.Item
                  name="roles"
                  label="角色"
                  rules={[{ required: true, message: "请选择角色" }]}
                >
                  <Select
                    mode="multiple"
                    options={roleOptions}
                    loading={roleQuery.isLoading}
                    placeholder="选择初始角色"
                  />
                </Form.Item>

                <Form.Item style={{ marginBottom: 0 }}>
                  <div className="split-actions">
                    <Button
                      onClick={() => {
                        navigate("/admin/users");
                      }}
                    >
                      取消
                    </Button>
                    <Button
                      type="primary"
                      htmlType="submit"
                      icon={<PlusOutlined />}
                      loading={createMutation.isPending}
                    >
                      创建用户
                    </Button>
                  </div>
                </Form.Item>
              </Form>
            </div>

            <aside className="split-create-aside">
              <section className="split-side-card">
                <Typography.Text className="split-side-card__title">账号摘要</Typography.Text>
                <div className="split-side-metrics">
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">邮箱</span>
                    <span className="split-side-metric__value">
                      {watchedEmail.trim() || "未填写"}
                    </span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">角色数量</span>
                    <span className="split-side-metric__value">{watchedRoles.length}</span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">默认角色</span>
                    <span className="split-side-metric__value">
                      {watchedRoles[0] ?? "user"}
                    </span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">密码状态</span>
                    <span className="split-side-metric__value">
                      {watchedPassword ? "已设置" : "未设置"}
                    </span>
                  </div>
                </div>
              </section>

              <section className="split-side-card">
                <Typography.Text className="split-side-card__title">后续动作</Typography.Text>
                <div className="split-side-list">
                  <div className="split-side-list__item">创建后回到列表页继续调整状态和授权范围。</div>
                  <div className="split-side-list__item">普通用户建议先从 user 角色开始，再逐步追加权限。</div>
                  <div className="split-side-list__item">如果需要绑定知识库访问权限，在用户列表中继续操作。</div>
                </div>
              </section>
            </aside>
          </div>
        </div>
      </Card>
    </div>
  );
}
