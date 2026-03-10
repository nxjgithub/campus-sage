import { useEffect, useMemo, useState } from "react";
import {
  ArrowRightOutlined,
  DeleteOutlined,
  EditOutlined,
  InfoCircleOutlined,
  KeyOutlined,
  LockOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  SearchOutlined,
  SettingOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message
} from "antd";
import { useNavigate } from "react-router-dom";
import { fetchKbList } from "../../shared/api/modules/kb";
import { fetchRoleList } from "../../shared/api/modules/roles";
import {
  deleteUserKbAccess,
  fetchUserKbAccess,
  fetchUserList,
  KbAccessItem,
  replaceUserKbAccess,
  upsertUserKbAccess,
  updateUser,
  UserListItem
} from "../../shared/api/modules/users";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
import { CompactPageHero } from "../../shared/components/CompactPageHero";
import { DonutMetricChart, MetricBarChart } from "../../shared/components/MetricCharts";
import { OpsPane } from "../../shared/components/OpsWorkbench";
import { PageState } from "../../shared/components/PageState";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";

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
type TableDensity = "middle" | "small";
type RoleFilter = "all" | "admin" | "user";

function resolveStatusColor(status: EditUserValues["status"]) {
  if (status === "active") {
    return "success";
  }
  if (status === "disabled") {
    return "warning";
  }
  return "default";
}

export function UsersPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");
  const [tableDensity, setTableDensity] = useState<TableDensity>("small");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const usersQuery = useQuery({
    queryKey: ["users", "list", filterStatus, filterKeyword, page, pageSize],
    queryFn: async () =>
      fetchUserList({
        status: filterStatus,
        keyword: filterKeyword || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize
      })
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

  const updateUserMutation = useMutation({
    mutationFn: async (values: EditUserValues) => {
      if (!editingUser) {
        throw new Error("缺少用户信息");
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
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const accessMutation = useMutation({
    mutationFn: async (values: KbAccessValues) => {
      if (!accessUser) {
        throw new Error("缺少用户信息");
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
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const deleteAccessMutation = useMutation({
    mutationFn: async (kbId: string) => {
      if (!accessUser) {
        throw new Error("缺少用户信息");
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
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const replaceAccessMutation = useMutation({
    mutationFn: async (values: KbAccessBulkValues) => {
      if (!accessUser) {
        throw new Error("缺少用户信息");
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
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const firstError = useMemo(() => {
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

  const activeCount = usersQuery.data?.items.filter((item) => item.status === "active").length ?? 0;
  const disabledCount =
    usersQuery.data?.items.filter((item) => item.status === "disabled").length ?? 0;
  const adminCount =
    usersQuery.data?.items.filter((item) => item.roles.includes("admin")).length ?? 0;
  const filteredUsers = useMemo(() => {
    const items = usersQuery.data?.items ?? [];
    if (roleFilter === "all") {
      return items;
    }
    return items.filter((item) =>
      roleFilter === "admin" ? item.roles.includes("admin") : item.roles.includes("user")
    );
  }, [roleFilter, usersQuery.data?.items]);
  const kbNameMap = useMemo(() => {
    return new Map((kbQuery.data?.items ?? []).map((item) => [item.kb_id, item.name]));
  }, [kbQuery.data?.items]);
  const statusChartItems = [
    { key: "active", label: "活跃", value: activeCount, color: "#16a34a" },
    { key: "disabled", label: "禁用", value: disabledCount, color: "#f59e0b" },
    {
      key: "deleted",
      label: "已删除",
      value: usersQuery.data?.items.filter((item) => item.status === "deleted").length ?? 0,
      color: "#94a3b8"
    }
  ];
  const roleChartItems = [
    { key: "admin", label: "管理员", value: adminCount, color: "#2563eb" },
    {
      key: "user",
      label: "普通用户",
      value: usersQuery.data?.items.filter((item) => item.roles.includes("user")).length ?? 0,
      color: "#0ea5a0"
    }
  ];

  return (
    <div className="page-stack">
      {firstError ? <RequestErrorAlert error={firstError} /> : null}

      <CompactPageHero
        kicker="账号与授权"
        title="用户与权限中心"
        description="当前页面只负责列表维护、状态调整和知识库授权；创建动作已拆到独立页面，减少同屏表单堆叠。"
        stats={[
          { label: "用户", value: usersQuery.data?.items.length ?? 0 },
          { label: "活跃", value: activeCount },
          { label: "禁用", value: disabledCount },
          { label: "管理员", value: adminCount }
        ]}
      />

      <div className="dashboard-grid">
        <Card className="card-soft" size="small" title="用户状态分布">
          <DonutMetricChart
            items={statusChartItems}
            centerLabel="用户"
            centerValue={usersQuery.data?.items.length ?? 0}
            emptyText="暂无用户状态数据"
          />
        </Card>
        <Card className="card-soft" size="small" title="角色对比">
          <MetricBarChart items={roleChartItems} emptyText="暂无角色分布数据" />
        </Card>
      </div>

      <Card className="card-soft split-manage-card">
        <OpsPane
          title={
            <Space size={8}>
              <TeamOutlined />
              <span>用户列表</span>
            </Space>
          }
          dense={tableDensity === "small"}
          extra={
            <Space>
              <Button
                type="primary"
                icon={<ArrowRightOutlined />}
                onClick={() => {
                  navigate("/admin/users/create");
                }}
              >
                前往创建
              </Button>
              <Input
                allowClear
                prefix={<SearchOutlined />}
                placeholder="按邮箱搜索"
                value={filterKeywordInput}
                onChange={(event) => setFilterKeywordInput(event.target.value)}
                style={{ width: 220 }}
              />
              <Select
                allowClear
                placeholder="状态筛选"
                value={filterStatus}
                options={STATUS_OPTIONS}
                style={{ width: 140 }}
                onChange={(value) => {
                  setFilterStatus(value);
                  setPage(1);
                }}
              />
              <Button
                shape="circle"
                icon={<SearchOutlined />}
                onClick={() => {
                  setFilterKeyword(filterKeywordInput.trim());
                  setPage(1);
                }}
                aria-label="查询用户"
              />
              <Button
                shape="circle"
                icon={<ReloadOutlined />}
                onClick={() => void usersQuery.refetch()}
                loading={usersQuery.isFetching}
                aria-label="刷新用户列表"
              />
            </Space>
          }
        >
          <div className="split-pane-copy split-pane-copy--compact">
            <Typography.Text className="split-pane-copy__title">
              列表页只处理维护与授权
            </Typography.Text>
            <Typography.Text className="split-pane-copy__desc">
              新账号创建已单独拆页，这里专注做筛选、状态编辑和知识库访问控制。
            </Typography.Text>
          </div>
          <div className="density-toolbar density-toolbar--clean">
            <Segmented<RoleFilter>
              value={roleFilter}
              options={[
                { label: "全部角色", value: "all" },
                { label: "仅管理员", value: "admin" },
                { label: "仅用户", value: "user" }
              ]}
              onChange={(value) => {
                setRoleFilter(value);
                setPage(1);
              }}
            />
            <div className="density-toolbar__group density-toolbar__group--meta">
              <Typography.Text className="density-meta">
                当前 {filteredUsers.length} / {usersQuery.data?.items.length ?? 0}
              </Typography.Text>
              <Segmented<TableDensity>
                size="small"
                value={tableDensity}
                options={[
                  { label: "舒适", value: "middle" },
                  { label: "紧凑", value: "small" }
                ]}
                onChange={(value) => {
                  setTableDensity(value);
                }}
              />
            </div>
          </div>
          <PageState status={userTableStatus}>
            <div className="ops-scroll-pane">
              <Table
                size={tableDensity}
                className={tableDensity === "small" ? "dense-table" : undefined}
                rowKey="user_id"
                dataSource={filteredUsers}
                pagination={{
                  current: page,
                  pageSize,
                  total: roleFilter === "all" ? usersQuery.data?.total ?? 0 : filteredUsers.length,
                  showSizeChanger: true,
                  pageSizeOptions: USER_PAGE_SIZE_OPTIONS.map(String),
                  onChange: (nextPage, nextPageSize) => {
                    setPage(nextPage);
                    setPageSize(nextPageSize);
                  }
                }}
                columns={[
                  {
                    title: "用户",
                    dataIndex: "email",
                    width: 280,
                    render: (value: string, record: UserListItem) => (
                      <Space direction="vertical" size={2}>
                        <Typography.Text strong>{value}</Typography.Text>
                        <Typography.Text type="secondary">创建于 {record.created_at}</Typography.Text>
                      </Space>
                    )
                  },
                  {
                    title: "状态",
                    dataIndex: "status",
                    width: 120,
                    render: (value: EditUserValues["status"]) => (
                      <Tag color={resolveStatusColor(value)}>{value}</Tag>
                    )
                  },
                  {
                    title: "角色",
                    dataIndex: "roles",
                    render: (roles: string[]) => (
                      <Space wrap>
                        {roles.map((role) => (
                          <Tag key={role} color={role === "admin" ? "processing" : "default"}>
                            {role}
                          </Tag>
                        ))}
                      </Space>
                    )
                  },
                  {
                    title: "操作",
                    key: "actions",
                    width: 220,
                    render: (_, record: UserListItem) => (
                      <Space>
                        <Tooltip title="编辑">
                          <Button
                            size="small"
                            shape="circle"
                            icon={<EditOutlined />}
                            onClick={() => {
                              setEditingUser(record);
                            }}
                            aria-label="编辑用户"
                          />
                        </Tooltip>
                        <Tooltip title="知识库权限">
                          <Button
                            size="small"
                            shape="circle"
                            icon={<SafetyCertificateOutlined />}
                            onClick={() => {
                              setAccessUser(record);
                            }}
                            aria-label="配置知识库权限"
                          />
                        </Tooltip>
                      </Space>
                    )
                  }
                ]}
              />
            </div>
          </PageState>
        </OpsPane>
      </Card>

      <Modal
        title={
          <Space size={8}>
            <SettingOutlined />
            <span>编辑用户</span>
          </Space>
        }
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
        title={
          <Space size={8}>
            <SafetyCertificateOutlined />
            <span>知识库访问权限</span>
          </Space>
        }
        open={Boolean(accessUser)}
        footer={null}
        width={860}
        onCancel={() => {
          setAccessUser(null);
          accessForm.resetFields();
          bulkAccessForm.resetFields();
        }}
      >
        <div className="compact-modal-meta">
          <Tag icon={<SafetyCertificateOutlined />} color="processing">
            {accessUser?.email ?? "-"}
          </Tag>
        </div>
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
                  label: item.name
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
              <Tooltip title="新增或更新权限">
                <Button
                  type="primary"
                  htmlType="submit"
                  shape="circle"
                  className="compact-primary-action"
                  icon={<KeyOutlined />}
                  loading={accessMutation.isPending}
                  aria-label="新增或更新权限"
                />
              </Tooltip>
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
            {
              title: "知识库",
              dataIndex: "kb_id",
              render: (value: string) => kbNameMap.get(value) ?? "未知知识库"
            },
            {
              title: "访问级别",
              dataIndex: "access_level",
              width: 140,
              render: (value: KbAccessValues["access_level"]) => <Tag>{value}</Tag>
            },
            {
              title: "操作",
              key: "actions",
              width: 120,
              render: (_, record) => (
                <Tooltip title="撤销权限">
                  <span>
                    <ConfirmAction
                      title="确认撤销该权限？"
                      okText="确认撤销"
                      cancelText="返回"
                      onConfirm={() => {
                        deleteAccessMutation.mutate(record.kb_id);
                      }}
                      buttonText=""
                      icon={<DeleteOutlined />}
                      danger
                      size="small"
                      shape="circle"
                      loading={deleteAccessMutation.isPending}
                      ariaLabel="撤销权限"
                    />
                  </span>
                </Tooltip>
              )
            }
          ]}
          locale={{ emptyText: "暂无权限记录" }}
        />

        <Card
          title={
            <Space size={8}>
              <LockOutlined />
              <span>批量覆盖权限列表</span>
              <Tooltip title="提交后会替换该用户当前全部知识库权限。">
                <InfoCircleOutlined />
              </Tooltip>
            </Space>
          }
          size="small"
          style={{ marginTop: 12 }}
          className="card-inset"
        >
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
                            label: item.name
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
                        <Tooltip title="移除">
                          <Button
                            shape="circle"
                            icon={<DeleteOutlined />}
                            onClick={() => {
                              remove(field.name);
                            }}
                            aria-label="移除权限项"
                          />
                        </Tooltip>
                      </Form.Item>
                    </Space>
                  ))}
                  <Space>
                    <Tooltip title="添加一条">
                      <Button
                        shape="circle"
                        icon={<PlusOutlined />}
                        onClick={() => {
                          add({ kb_id: "", access_level: "read" });
                        }}
                        aria-label="添加权限项"
                      />
                    </Tooltip>
                    <Tooltip title="批量覆盖保存">
                      <Button
                        type="primary"
                        htmlType="submit"
                        shape="circle"
                        className="compact-primary-action"
                        icon={<SaveOutlined />}
                        loading={replaceAccessMutation.isPending}
                        aria-label="批量覆盖保存"
                      />
                    </Tooltip>
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
