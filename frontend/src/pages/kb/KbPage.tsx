import { useEffect, useMemo, useState } from "react";
import {
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  ThunderboltOutlined
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message
} from "antd";
import {
  createKb,
  deleteKb,
  fetchKbDetail,
  fetchKbList,
  KbConfig,
  updateKb
} from "../../shared/api/modules/kb";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
import { OpsPane, OpsWorkbench } from "../../shared/components/OpsWorkbench";
import { PageState } from "../../shared/components/PageState";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";

interface KbFormValues {
  name: string;
  description?: string;
  visibility: "public" | "internal" | "admin";
  topk: number;
  threshold: number;
  rerank_enabled: boolean;
  max_context_tokens: number;
  min_context_chars: number;
  min_keyword_coverage: number;
}

interface KbEditValues {
  description?: string;
  visibility: "public" | "internal" | "admin";
  topk: number;
  threshold: number;
  rerank_enabled: boolean;
  max_context_tokens: number;
  min_context_chars: number;
  min_keyword_coverage: number;
}

type VisibilityFilter = "all" | "public" | "internal" | "admin";
type TableDensity = "middle" | "small";

function resolveVisibilityColor(value: VisibilityFilter | KbFormValues["visibility"]) {
  if (value === "public") {
    return "success";
  }
  if (value === "admin") {
    return "error";
  }
  return "processing";
}

export function KbPage() {
  const queryClient = useQueryClient();
  const [createForm] = Form.useForm<KbFormValues>();
  const [editForm] = Form.useForm<KbEditValues>();
  const [editingKbId, setEditingKbId] = useState<string | null>(null);
  const [keyword, setKeyword] = useState("");
  const [visibilityFilter, setVisibilityFilter] = useState<VisibilityFilter>("all");
  const [tableDensity, setTableDensity] = useState<TableDensity>("small");
  const [onlyRerankEnabled, setOnlyRerankEnabled] = useState(false);

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList
  });

  const kbDetailQuery = useQuery({
    queryKey: ["kb", "detail", editingKbId],
    queryFn: async () => fetchKbDetail(editingKbId as string),
    enabled: Boolean(editingKbId)
  });

  useEffect(() => {
    if (!kbDetailQuery.data) {
      return;
    }
    editForm.setFieldsValue({
      description: kbDetailQuery.data.description ?? undefined,
      visibility: kbDetailQuery.data.visibility,
      topk: kbDetailQuery.data.config.topk,
      threshold: kbDetailQuery.data.config.threshold,
      rerank_enabled: kbDetailQuery.data.config.rerank_enabled,
      max_context_tokens: kbDetailQuery.data.config.max_context_tokens,
      min_context_chars: kbDetailQuery.data.config.min_context_chars ?? 20,
      min_keyword_coverage: kbDetailQuery.data.config.min_keyword_coverage ?? 0.3
    });
  }, [editForm, kbDetailQuery.data]);

  const createMutation = useMutation({
    mutationFn: async (values: KbFormValues) => {
      const config: KbConfig = {
        topk: values.topk,
        threshold: values.threshold,
        rerank_enabled: values.rerank_enabled,
        max_context_tokens: values.max_context_tokens,
        min_context_chars: values.min_context_chars,
        min_keyword_coverage: values.min_keyword_coverage
      };
      return createKb({
        name: values.name.trim(),
        description: values.description?.trim() || null,
        visibility: values.visibility,
        config
      });
    },
    onSuccess: async () => {
      message.success("知识库创建成功");
      createForm.resetFields();
      await queryClient.invalidateQueries({ queryKey: ["kb", "list"] });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const updateMutation = useMutation({
    mutationFn: async (values: KbEditValues) => {
      if (!editingKbId) {
        throw new Error("缺少知识库信息");
      }
      return updateKb(editingKbId, {
        description: values.description?.trim() || null,
        visibility: values.visibility,
        config: {
          topk: values.topk,
          threshold: values.threshold,
          rerank_enabled: values.rerank_enabled,
          max_context_tokens: values.max_context_tokens,
          min_context_chars: values.min_context_chars,
          min_keyword_coverage: values.min_keyword_coverage
        }
      });
    },
    onSuccess: async () => {
      message.success("知识库更新成功");
      setEditingKbId(null);
      await queryClient.invalidateQueries({ queryKey: ["kb", "list"] });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const deleteMutation = useMutation({
    mutationFn: async (kbId: string) => deleteKb(kbId),
    onSuccess: async () => {
      message.success("知识库已删除");
      await queryClient.invalidateQueries({ queryKey: ["kb", "list"] });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const status = useMemo(() => {
    if (kbQuery.isLoading) return "loading" as const;
    if (kbQuery.isError) return "error" as const;
    if (!kbQuery.data?.items?.length) return "empty" as const;
    return "success" as const;
  }, [kbQuery.data?.items, kbQuery.isError, kbQuery.isLoading]);

  const publicCount = kbQuery.data?.items.filter((item) => item.visibility === "public").length ?? 0;
  const internalCount =
    kbQuery.data?.items.filter((item) => item.visibility === "internal").length ?? 0;
  const adminCount = kbQuery.data?.items.filter((item) => item.visibility === "admin").length ?? 0;

  const filteredItems = useMemo(() => {
    const base = kbQuery.data?.items ?? [];
    return base.filter((item) => {
      if (visibilityFilter !== "all" && item.visibility !== visibilityFilter) {
        return false;
      }
      if (onlyRerankEnabled && !item.config?.rerank_enabled) {
        return false;
      }
      if (!keyword.trim()) {
        return true;
      }
      const target = `${item.name} ${item.description ?? ""}`.toLowerCase();
      return target.includes(keyword.toLowerCase());
    });
  }, [kbQuery.data?.items, keyword, visibilityFilter, onlyRerankEnabled]);

  return (
    <div className="page-stack">
      {(createMutation.isError || updateMutation.isError || deleteMutation.isError) && (
        <RequestErrorAlert
          error={normalizeApiError(
            createMutation.error ?? updateMutation.error ?? deleteMutation.error
          )}
        />
      )}

      <Card className="hero-card">
        <div className="hero-layout">
          <div>
            <div className="hero-kicker">管理端 / 知识库治理</div>
            <Typography.Title level={4} className="hero-title">
              知识库配置中心
            </Typography.Title>
            <Typography.Text className="hero-desc">
              统一控制知识库可见性、检索阈值、重排开关与上下文预算，避免策略分散在多个页面。
            </Typography.Text>
            <div className="hero-note" style={{ marginTop: 14 }}>
              <span className="hero-note__item">创建后可立即进入文档入库</span>
              <span className="hero-note__item">列表支持按可见性与重排策略筛选</span>
              <span className="hero-note__item">编辑窗口集中维护检索契约参数</span>
            </div>
          </div>
          <div className="summary-grid">
            <div className="summary-item">
              <div className="summary-item-label">知识库总数</div>
              <div className="summary-item-value">{kbQuery.data?.items.length ?? 0}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">Public</div>
              <div className="summary-item-value">{publicCount}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">Internal</div>
              <div className="summary-item-value">{internalCount}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">Admin</div>
              <div className="summary-item-value">{adminCount}</div>
            </div>
          </div>
        </div>
      </Card>

      <OpsWorkbench
        left={
          <OpsPane
            title={
              <Space size={8}>
                <PlusOutlined />
                <span>创建知识库</span>
              </Space>
            }
            introTitle="先定义访问边界，再定义检索策略"
            introDescription="建议先确定知识库用途与可见性，再设置 TopK、阈值和最小上下文要求，避免后续问答表现漂移。"
          >
              <Form<KbFormValues>
                form={createForm}
                layout="vertical"
                initialValues={{
                  visibility: "internal",
                  topk: 5,
                  threshold: 0.25,
                  rerank_enabled: false,
                  max_context_tokens: 3000,
                  min_context_chars: 20,
                  min_keyword_coverage: 0.3
                }}
                onFinish={(values) => createMutation.mutate(values)}
              >
                <Form.Item
                  name="name"
                  label="知识库名称"
                  rules={[{ required: true, message: "请输入名称" }]}
                >
                  <Input placeholder="例如：教务知识库" />
                </Form.Item>
                <Form.Item name="description" label="知识库说明">
                  <Input.TextArea rows={2} placeholder="可选" />
                </Form.Item>
                <Form.Item name="visibility" label="可见性" rules={[{ required: true }]}>
                  <Select
                    options={[
                      { value: "public", label: "public" },
                      { value: "internal", label: "internal" },
                      { value: "admin", label: "admin" }
                    ]}
                  />
                </Form.Item>
                <Card size="small" className="card-inset" title="检索参数">
                  <Space wrap>
                    <Form.Item name="topk" label="TopK">
                      <InputNumber min={1} />
                    </Form.Item>
                    <Form.Item name="threshold" label="阈值">
                      <InputNumber min={0} max={1} step={0.01} />
                    </Form.Item>
                    <Form.Item name="rerank_enabled" label="启用重排">
                      <Select
                        options={[
                          { value: true, label: "true" },
                          { value: false, label: "false" }
                        ]}
                      />
                    </Form.Item>
                    <Form.Item name="max_context_tokens" label="最大上下文">
                      <InputNumber min={100} />
                    </Form.Item>
                    <Form.Item name="min_context_chars" label="最小上下文长度">
                      <InputNumber min={1} />
                    </Form.Item>
                    <Form.Item name="min_keyword_coverage" label="最小关键词覆盖率">
                      <InputNumber min={0} max={1} step={0.05} />
                    </Form.Item>
                  </Space>
                </Card>
                <Form.Item style={{ marginTop: 12 }}>
                  <Button
                    type="primary"
                    htmlType="submit"
                    icon={<PlusOutlined />}
                    loading={createMutation.isPending}
                  >
                    创建
                  </Button>
                </Form.Item>
              </Form>
          </OpsPane>
        }
        right={
          <OpsPane
            title={
              <Space size={8}>
                <DatabaseOutlined />
                <span>知识库列表</span>
              </Space>
            }
            dense={tableDensity === "small"}
            extra={
              <Button
                icon={<ReloadOutlined />}
                onClick={() => void kbQuery.refetch()}
                loading={kbQuery.isFetching}
              >
                刷新
              </Button>
            }
          >
            <div className="density-toolbar">
              <Space wrap>
                <Input
                  prefix={<SearchOutlined />}
                  placeholder="搜索名称 / 描述"
                  allowClear
                  value={keyword}
                  onChange={(event) => {
                    setKeyword(event.target.value);
                  }}
                  style={{ width: 220 }}
                />
                <Segmented<VisibilityFilter>
                  value={visibilityFilter}
                  options={[
                    { label: "全部", value: "all" },
                    { label: "Public", value: "public" },
                    { label: "Internal", value: "internal" },
                    { label: "Admin", value: "admin" }
                  ]}
                  onChange={(value) => {
                    setVisibilityFilter(value);
                  }}
                />
                <Button
                  icon={<ThunderboltOutlined />}
                  onClick={() => {
                    setOnlyRerankEnabled((prev) => !prev);
                  }}
                  type={onlyRerankEnabled ? "primary" : "default"}
                >
                  仅看重排开启
                </Button>
              </Space>
              <Space>
                <Typography.Text className="density-meta">
                  当前 {filteredItems.length} / {kbQuery.data?.items.length ?? 0}
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
              </Space>
            </div>
            {kbQuery.isError ? <RequestErrorAlert error={normalizeApiError(kbQuery.error)} /> : null}
            <PageState status={status}>
              <div className="ops-scroll-pane">
                <Table
                  size={tableDensity}
                  className={tableDensity === "small" ? "dense-table" : undefined}
                  rowKey="kb_id"
                  dataSource={filteredItems}
                  pagination={false}
                  columns={[
                    {
                      title: "知识库",
                      dataIndex: "name",
                      render: (_value: string, record) => (
                        <Space direction="vertical" size={2}>
                          <Typography.Text strong>{record.name}</Typography.Text>
                          <Typography.Text type="secondary">
                            {record.description || "暂无说明"}
                          </Typography.Text>
                        </Space>
                      )
                    },
                    {
                      title: "策略",
                      key: "retrieval",
                      width: 260,
                      render: (_, record) => (
                        <Space size={4} wrap>
                          <Tag>TopK {record.config?.topk ?? "-"}</Tag>
                          <Tag>阈值 {record.config?.threshold ?? "-"}</Tag>
                          <Tag color={record.config?.rerank_enabled ? "processing" : "default"}>
                            重排 {record.config?.rerank_enabled ? "on" : "off"}
                          </Tag>
                        </Space>
                      )
                    },
                    {
                      title: "可见性",
                      dataIndex: "visibility",
                      width: 120,
                      render: (value: KbEditValues["visibility"]) => (
                        <Tag color={resolveVisibilityColor(value)} icon={<EyeOutlined />}>
                          {value}
                        </Tag>
                      )
                    },
                    {
                      title: "更新时间",
                      dataIndex: "updated_at",
                      width: 220,
                      render: (value: string) => (
                        <Typography.Text type="secondary">{value}</Typography.Text>
                      )
                    },
                    {
                      title: "操作",
                      key: "actions",
                      width: 220,
                      render: (_, record: { kb_id: string }) => (
                        <Space>
                          <Button
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => {
                              setEditingKbId(record.kb_id);
                            }}
                          >
                            编辑
                          </Button>
                          <ConfirmAction
                            title="确认删除该知识库？"
                            okText="确认删除"
                            cancelText="取消"
                            onConfirm={() => deleteMutation.mutate(record.kb_id)}
                            buttonText="删除"
                            icon={<DeleteOutlined />}
                            danger
                            size="small"
                            loading={deleteMutation.isPending}
                          />
                        </Space>
                      )
                    }
                  ]}
                />
              </div>
            </PageState>
          </OpsPane>
        }
      />

      <Modal
        title={
          <Space size={8}>
            <SettingOutlined />
            <span>编辑知识库</span>
          </Space>
        }
        open={Boolean(editingKbId)}
        onCancel={() => setEditingKbId(null)}
        confirmLoading={updateMutation.isPending}
        onOk={() => {
          void editForm.submit();
        }}
      >
        {kbDetailQuery.isError ? <RequestErrorAlert error={normalizeApiError(kbDetailQuery.error)} /> : null}
        <Form<KbEditValues>
          form={editForm}
          layout="vertical"
          onFinish={(values) => updateMutation.mutate(values)}
        >
          <Form.Item name="description" label="知识库说明">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="visibility" label="可见性" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "public", label: "public" },
                { value: "internal", label: "internal" },
                { value: "admin", label: "admin" }
              ]}
            />
          </Form.Item>
          <Space wrap>
            <Form.Item name="topk" label="TopK">
              <InputNumber min={1} />
            </Form.Item>
            <Form.Item name="threshold" label="阈值">
              <InputNumber min={0} max={1} step={0.01} />
            </Form.Item>
            <Form.Item name="rerank_enabled" label="启用重排">
              <Select options={[{ value: true, label: "true" }, { value: false, label: "false" }]} />
            </Form.Item>
            <Form.Item name="max_context_tokens" label="最大上下文">
              <InputNumber min={100} />
            </Form.Item>
            <Form.Item name="min_context_chars" label="最小上下文长度">
              <InputNumber min={1} />
            </Form.Item>
            <Form.Item name="min_keyword_coverage" label="最小关键词覆盖率">
              <InputNumber min={0} max={1} step={0.05} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
