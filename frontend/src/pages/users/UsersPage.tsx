import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message
} from "antd";
import { fetchKbList } from "../../shared/api/modules/kb";
import { fetchRoleList } from "../../shared/api/modules/roles";
import {
  createUser,
  deleteUserKbAccess,
  fetchUserKbAccess,
  fetchUserList,
  KbAccessItem,
  replaceUserKbAccess,
  upsertUserKbAccess,
  updateUser,
  UserListItem
} from "../../shared/api/modules/users";
import { normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
import { PageState } from "../../shared/components/PageState";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";

interface CreateUserValues {
  email: string;
  password: string;
  roles: string[];
}

interface EditUserValues {
  status: "active" | "disabled" | "deleted";
  roles: string[];
  password?: string;
}

interface KbAccessValues {
  kb_id: string;
  access_level: "read" | "write" | "admin";
}

interface KbAccessBulkValues {
  items: KbAccessItem[];
}

const STATUS_OPTIONS = [
  { value: "active", label: "active" },
  { value: "disabled", label: "disabled" },
  { value: "deleted", label: "deleted" }
];

const ACCESS_LEVEL_OPTIONS = [
  { value: "read", label: "read" },
  { value: "write", label: "write" },
  { value: "admin", label: "admin" }
];

const USER_PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export function UsersPage() {
  const queryClient = useQueryClient();
  const [createForm] = Form.useForm<CreateUserValues>();
  const [editForm] = Form.useForm<EditUserValues>();
  const [accessForm] = Form.useForm<KbAccessValues>();
  const [bulkAccessForm] = Form.useForm<KbAccessBulkValues>();
  const [editingUser, setEditingUser] = useState<UserListItem | null>(null);
  const [accessUser, setAccessUser] = useState<UserListItem | null>(null);
  const [filterKeywordInput, setFilterKeywordInput] = useState("");
  const [filterKeyword, setFilterKeyword] = useState("");
  const [filterStatus, setFilterStatus] = useState<"active" | "disabled" | "deleted" | undefined>(
    undefined
  );
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const usersQuery = useQuery({
    queryKey: ["users", "list", filterStatus, filterKeyword, page, pageSize],
    queryFn: async () => {
      return fetchUserList({
        status: filterStatus,
        keyword: filterKeyword || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize
      });
    }
  });

  const roleQuery = useQuery({
    queryKey: ["roles", "list"],
    queryFn: fetchRoleList
  });

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList
  });

  const accessQuery = useQuery({
    queryKey: ["users", "kb-access", accessUser?.user_id],
    queryFn: async () => fetchUserKbAccess(accessUser?.user_id as string),
    enabled: Boolean(accessUser?.user_id)
  });

  useEffect(() => {
    if (!editingUser) {
      return;
    }
    editForm.setFieldsValue({
      status: editingUser.status,
      roles: editingUser.roles
    });
  }, [editForm, editingUser]);

  useEffect(() => {
    if (!accessQuery.data) {
      return;
    }
    const items = accessQuery.data.items;
    bulkAccessForm.setFieldsValue({
      items: items.length ? items : [{ kb_id: "", access_level: "read" }]
    });
  }, [accessQuery.data, bulkAccessForm]);

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
    mutationFn: async (values: CreateUserValues) => {
      return createUser({
        email: values.email.trim(),
        password: values.password,
        roles: values.roles
      });
    },
    onSuccess: async () => {
      message.success("用户创建成功");
      createForm.resetFields();
      createForm.setFieldValue("roles", ["user"]);
      await queryClient.invalidateQueries({ queryKey: ["users", "list"] });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  const updateUserMutation = useMutation({
    mutationFn: async (values: EditUserValues) => {
      if (!editingUser) {
        throw new Error("缺少用户 ID");
      }
      return updateUser(editingUser.user_id, {
        status: values.status,
        roles: values.roles,
        password: values.password?.trim() || undefined
      });
    },
    onSuccess: async () => {
      message.success("用户信息更新成功");
      setEditingUser(null);
      await queryClient.invalidateQueries({ queryKey: ["users", "list"] });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  const accessMutation = useMutation({
    mutationFn: async (values: KbAccessValues) => {
      if (!accessUser) {
        throw new Error("缺少用户 ID");
      }
      return upsertUserKbAccess(accessUser.user_id, values);
    },
    onSuccess: async () => {
      message.success("知识库权限已更新");
      accessForm.resetFields();
      await queryClient.invalidateQueries({
        queryKey: ["users", "kb-access", accessUser?.user_id]
      });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  const deleteAccessMutation = useMutation({
    mutationFn: async (kbId: string) => {
      if (!accessUser) {
        throw new Error("缺少用户 ID");
      }
      return deleteUserKbAccess(accessUser.user_id, kbId);
    },
    onSuccess: async () => {
      message.success("权限已撤销");
      await queryClient.invalidateQueries({
        queryKey: ["users", "kb-access", accessUser?.user_id]
      });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  const replaceAccessMutation = useMutation({
    mutationFn: async (values: KbAccessBulkValues) => {
      if (!accessUser) {
        throw new Error("缺少用户 ID");
      }
      const validItems = (values.items ?? []).filter((item) => item.kb_id && item.access_level);
      return replaceUserKbAccess(accessUser.user_id, { items: validItems });
    },
    onSuccess: async () => {
      message.success("权限列表已批量更新");
      await queryClient.invalidateQueries({
        queryKey: ["users", "kb-access", accessUser?.user_id]
      });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  const firstError = useMemo(() => {
    if (createMutation.isError) return normalizeApiError(createMutation.error);
    if (updateUserMutation.isError) return normalizeApiError(updateUserMutation.error);
    if (accessMutation.isError) return normalizeApiError(accessMutation.error);
    if (deleteAccessMutation.isError) return normalizeApiError(deleteAccessMutation.error);
    if (replaceAccessMutation.isError) return normalizeApiError(replaceAccessMutation.error);
    if (usersQuery.isError) return normalizeApiError(usersQuery.error);
    if (kbQuery.isError) return normalizeApiError(kbQuery.error);
    if (roleQuery.isError) return normalizeApiError(roleQuery.error);
    if (accessQuery.isError) return normalizeApiError(accessQuery.error);
    return null;
  }, [
    accessMutation.error,
    accessMutation.isError,
    accessQuery.error,
    accessQuery.isError,
    createMutation.error,
    createMutation.isError,
    deleteAccessMutation.error,
    deleteAccessMutation.isError,
    kbQuery.error,
    kbQuery.isError,
    replaceAccessMutation.error,
    replaceAccessMutation.isError,
    roleQuery.error,
    roleQuery.isError,
    updateUserMutation.error,
    updateUserMutation.isError,
    usersQuery.error,
    usersQuery.isError
  ]);

  const userTableStatus = useMemo(() => {
    if (usersQuery.isLoading) return "loading" as const;
    if (usersQuery.isError) return "error" as const;
    if (!usersQuery.data?.items?.length) return "empty" as const;
    return "success" as const;
  }, [usersQuery.data?.items, usersQuery.isError, usersQuery.isLoading]);

  const activeCount =
    usersQuery.data?.items.filter((item) => item.status === "active").length ?? 0;
  const disabledCount =
    usersQuery.data?.items.filter((item) => item.status === "disabled").length ?? 0;
  const adminCount =
    usersQuery.data?.items.filter((item) => item.roles.includes("admin")).length ?? 0;

  return (
    <div className="page-stack">
      {firstError ? <RequestErrorAlert error={firstError} /> : null}

      <Card className="hero-card">
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Typography.Title level={4} className="hero-title">
            用户与权限中心
          </Typography.Title>
          <Typography.Text className="hero-desc">
            管理账号生命周期、角色分配、KB 访问授权与批量权限替换。
          </Typography.Text>
          <div className="summary-grid">
            <div className="summary-item">
              <div className="summary-item-label">当前页用户数</div>
              <div className="summary-item-value">{usersQuery.data?.items.length ?? 0}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">活跃账号</div>
              <div className="summary-item-value">{activeCount}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">禁用账号</div>
              <div className="summary-item-value">{disabledCount}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">管理员账号</div>
              <div className="summary-item-value">{adminCount}</div>
            </div>
          </div>
        </Space>
      </Card>

      <Card title="创建用户" className="card-soft">
        <Form<CreateUserValues>
          form={createForm}
          layout="vertical"
          initialValues={{ roles: ["user"] }}
          onFinish={(values) => {
            createMutation.mutate(values);
          }}
        >
          <Space wrap size={16} style={{ width: "100%" }}>
            <Form.Item
              name="email"
              label="邮箱"
              rules={[
                { required: true, message: "请输入邮箱" },
                { type: "email", message: "邮箱格式不正确" }
              ]}
              style={{ minWidth: 280 }}
            >
              <Input placeholder="user@example.com" />
            </Form.Item>
            <Form.Item
              name="password"
              label="初始密码"
              rules={[{ required: true, message: "请输入初始密码" }]}
              style={{ minWidth: 240 }}
            >
              <Input.Password placeholder="请包含字母与数字" />
            </Form.Item>
            <Form.Item
              name="roles"
              label="角色"
              rules={[{ required: true, message: "请选择角色" }]}
              style={{ minWidth: 220 }}
            >
              <Select mode="multiple" options={roleOptions} />
            </Form.Item>
          </Space>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
              创建用户
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card
        title="用户列表"
        className="card-soft"
        extra={
          <Space>
            <Input
              allowClear
              placeholder="按邮箱/用户ID搜索"
              value={filterKeywordInput}
              onChange={(event) => setFilterKeywordInput(event.target.value)}
              style={{ width: 220 }}
            />
            <Select
              allowClear
              placeholder="状态筛选"
              value={filterStatus}
              options={STATUS_OPTIONS}
              style={{ width: 150 }}
              onChange={(value) => {
                setFilterStatus(value);
                setPage(1);
              }}
            />
            <Button
              onClick={() => {
                setFilterKeyword(filterKeywordInput.trim());
                setPage(1);
              }}
            >
              查询
            </Button>
            <Button
              onClick={() => {
                void usersQuery.refetch();
              }}
              loading={usersQuery.isFetching}
            >
              刷新
            </Button>
          </Space>
        }
      >
        <PageState status={userTableStatus}>
          <Table
            rowKey="user_id"
            dataSource={usersQuery.data?.items ?? []}
            pagination={{
              current: page,
              pageSize,
              total: usersQuery.data?.total ?? 0,
              showSizeChanger: true,
              pageSizeOptions: USER_PAGE_SIZE_OPTIONS.map(String),
              onChange: (nextPage, nextPageSize) => {
                setPage(nextPage);
                setPageSize(nextPageSize);
              }
            }}
            columns={[
              { title: "用户ID", dataIndex: "user_id", width: 220 },
              { title: "邮箱", dataIndex: "email", width: 260 },
              {
                title: "状态",
                dataIndex: "status",
                width: 120,
                render: (value: string) => <Tag>{value}</Tag>
              },
              {
                title: "角色",
                dataIndex: "roles",
                render: (roles: string[]) => (
                  <Space wrap>
                    {roles.map((role) => (
                      <Tag key={role}>{role}</Tag>
                    ))}
                  </Space>
                )
              },
              { title: "创建时间", dataIndex: "created_at", width: 220 },
              {
                title: "操作",
                key: "actions",
                width: 260,
                render: (_, record: UserListItem) => (
                  <Space>
                    <Button
                      size="small"
                      onClick={() => {
                        setEditingUser(record);
                      }}
                    >
                      编辑
                    </Button>
                    <Button
                      size="small"
                      onClick={() => {
                        setAccessUser(record);
                      }}
                    >
                      KB权限
                    </Button>
                  </Space>
                )
              }
            ]}
          />
        </PageState>
      </Card>

      <Modal
        title="编辑用户"
        open={Boolean(editingUser)}
        onCancel={() => setEditingUser(null)}
        confirmLoading={updateUserMutation.isPending}
        onOk={() => {
          void editForm.submit();
        }}
      >
        <Form<EditUserValues>
          form={editForm}
          layout="vertical"
          onFinish={(values) => {
            updateUserMutation.mutate(values);
          }}
        >
          <Form.Item name="status" label="状态" rules={[{ required: true, message: "请选择状态" }]}>
            <Select options={STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item name="roles" label="角色" rules={[{ required: true, message: "请选择角色" }]}>
            <Select mode="multiple" options={roleOptions} />
          </Form.Item>
          <Form.Item name="password" label="重置密码（可选）">
            <Input.Password placeholder="留空表示不修改" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="知识库访问权限"
        open={Boolean(accessUser)}
        footer={null}
        width={860}
        onCancel={() => {
          setAccessUser(null);
          accessForm.resetFields();
          bulkAccessForm.resetFields();
        }}
      >
        <Typography.Paragraph type="secondary">
          当前用户：{accessUser?.email ?? "-"}
        </Typography.Paragraph>
        <Form<KbAccessValues>
          form={accessForm}
          layout="vertical"
          onFinish={(values) => {
            accessMutation.mutate(values);
          }}
        >
          <Space align="start" wrap>
            <Form.Item
              name="kb_id"
              label="知识库"
              rules={[{ required: true, message: "请选择知识库" }]}
              style={{ minWidth: 320 }}
            >
              <Select
                showSearch
                loading={kbQuery.isLoading}
                options={(kbQuery.data?.items ?? []).map((item) => ({
                  value: item.kb_id,
                  label: `${item.name} (${item.kb_id})`
                }))}
              />
            </Form.Item>
            <Form.Item
              name="access_level"
              label="访问级别"
              rules={[{ required: true, message: "请选择访问级别" }]}
              style={{ width: 160 }}
            >
              <Select options={ACCESS_LEVEL_OPTIONS} />
            </Form.Item>
            <Form.Item label=" " style={{ marginTop: 22 }}>
              <Button type="primary" htmlType="submit" loading={accessMutation.isPending}>
                新增/更新单条
              </Button>
            </Form.Item>
          </Space>
        </Form>

        <Table<KbAccessItem>
          rowKey="kb_id"
          size="small"
          loading={accessQuery.isLoading}
          dataSource={accessQuery.data?.items ?? []}
          pagination={false}
          columns={[
            { title: "kb_id", dataIndex: "kb_id" },
            { title: "访问级别", dataIndex: "access_level", width: 140 },
            {
              title: "操作",
              key: "actions",
              width: 120,
              render: (_, record) => (
                <ConfirmAction
                  title="确认撤销该权限？"
                  okText="确认撤销"
                  cancelText="返回"
                  onConfirm={() => {
                    deleteAccessMutation.mutate(record.kb_id);
                  }}
                  buttonText="撤销"
                  danger
                  size="small"
                  loading={deleteAccessMutation.isPending}
                />
              )
            }
          ]}
          locale={{ emptyText: "暂无权限记录" }}
        />

        <Card title="批量覆盖权限列表" size="small" style={{ marginTop: 12 }} className="card-inset">
          <Typography.Paragraph type="secondary">
            提交后会替换该用户当前全部 KB 权限，请谨慎操作。
          </Typography.Paragraph>
          <Form<KbAccessBulkValues>
            form={bulkAccessForm}
            layout="vertical"
            onFinish={(values) => {
              replaceAccessMutation.mutate(values);
            }}
          >
            <Form.List name="items">
              {(fields, { add, remove }) => (
                <Space direction="vertical" style={{ width: "100%" }}>
                  {fields.map((field) => (
                    <Space key={field.key} align="start" wrap>
                      <Form.Item
                        name={[field.name, "kb_id"]}
                        label="知识库"
                        rules={[{ required: true, message: "请选择知识库" }]}
                        style={{ minWidth: 320 }}
                      >
                        <Select
                          showSearch
                          options={(kbQuery.data?.items ?? []).map((item) => ({
                            value: item.kb_id,
                            label: `${item.name} (${item.kb_id})`
                          }))}
                        />
                      </Form.Item>
                      <Form.Item
                        name={[field.name, "access_level"]}
                        label="访问级别"
                        rules={[{ required: true, message: "请选择访问级别" }]}
                        style={{ width: 160 }}
                      >
                        <Select options={ACCESS_LEVEL_OPTIONS} />
                      </Form.Item>
                      <Form.Item label=" " style={{ marginTop: 22 }}>
                        <Button
                          onClick={() => {
                            remove(field.name);
                          }}
                        >
                          移除
                        </Button>
                      </Form.Item>
                    </Space>
                  ))}
                  <Space>
                    <Button
                      onClick={() => {
                        add({ kb_id: "", access_level: "read" });
                      }}
                    >
                      添加一条
                    </Button>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={replaceAccessMutation.isPending}
                    >
                      批量覆盖保存
                    </Button>
                  </Space>
                </Space>
              )}
            </Form.List>
          </Form>
        </Card>
      </Modal>
    </div>
  );
}
