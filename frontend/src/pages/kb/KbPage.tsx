import { useEffect, useMemo, useState } from "react";
import {
  ArrowRightOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
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
  Tooltip,
  Typography,
  message
} from "antd";
import { useNavigate } from "react-router-dom";
import { deleteKb, fetchKbDetail, fetchKbList, updateKb } from "../../shared/api/modules/kb";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
import { OpsPane } from "../../shared/components/OpsWorkbench";
import { PageState } from "../../shared/components/PageState";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import {
  formatDateParts,
  KbEditValues,
  resolveVisibilityColor,
  TableDensity,
  VisibilityFilter
} from "./kbShared";

export function KbPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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
      {(updateMutation.isError || deleteMutation.isError) && (
        <RequestErrorAlert error={normalizeApiError(updateMutation.error ?? deleteMutation.error)} />
      )}

      <Card className="card-soft kb-overview-card">
        <div className="kb-overview">
          <div className="kb-overview__copy">
            <div className="kb-overview__label-row">
              <span className="hero-kicker">知识库治理</span>
              <Typography.Text className="kb-overview__eyebrow">
                列表维护与创建分离
              </Typography.Text>
            </div>
            <Typography.Title level={3} className="hero-title">
              知识库列表与维护
            </Typography.Title>
            <Typography.Paragraph className="kb-overview__desc">
              当前页面只负责筛选、查看、编辑和删除。创建动作已经拆到独立页面，避免在同一视图里同时处理录入与治理。
            </Typography.Paragraph>
            <div className="kb-overview__notes">
              <span className="kb-overview__note">列表页专注筛选和维护</span>
              <span className="kb-overview__note">创建页专注录入和参数配置</span>
            </div>
            <div className="kb-overview__summary" aria-label="知识库概要统计">
              <div className="kb-overview-summary-item">
                <span className="kb-overview-summary-item__label">知识库</span>
                <span className="kb-overview-summary-item__value">{kbQuery.data?.items.length ?? 0}</span>
              </div>
              <div className="kb-overview-summary-item">
                <span className="kb-overview-summary-item__label">Public</span>
                <span className="kb-overview-summary-item__value">{publicCount}</span>
              </div>
              <div className="kb-overview-summary-item">
                <span className="kb-overview-summary-item__label">Internal</span>
                <span className="kb-overview-summary-item__value">{internalCount}</span>
              </div>
              <div className="kb-overview-summary-item">
                <span className="kb-overview-summary-item__label">Admin</span>
                <span className="kb-overview-summary-item__value">{adminCount}</span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card className="card-soft kb-list-card">
        <OpsPane
          title={
            <Space size={8}>
              <DatabaseOutlined />
              <span>知识库列表</span>
            </Space>
          }
          dense={tableDensity === "small"}
          extra={
            <Space size={8}>
              <Tooltip title="刷新">
                <Button
                  shape="circle"
                  icon={<ReloadOutlined />}
                  onClick={() => void kbQuery.refetch()}
                  loading={kbQuery.isFetching}
                  aria-label="刷新知识库列表"
                />
              </Tooltip>
            </Space>
          }
        >
          <div className="kb-pane-copy kb-pane-copy--compact">
            <Typography.Text className="kb-pane-copy__title">
              用搜索和筛选快速定位目标
            </Typography.Text>
          </div>
          <div className="kb-toolbar-stack">
            <div className="density-toolbar density-toolbar--clean kb-toolbar-stack__row">
              <div className="density-toolbar__group">
                <Input
                  prefix={<SearchOutlined />}
                  placeholder="搜索名称 / 描述"
                  allowClear
                  value={keyword}
                  onChange={(event) => {
                    setKeyword(event.target.value);
                  }}
                  className="kb-toolbar-stack__search"
                />
              </div>
              <div className="density-toolbar__group density-toolbar__group--meta">
                <Button
                  type="primary"
                  icon={<ArrowRightOutlined />}
                  onClick={() => {
                    navigate("/admin/kb/create");
                  }}
                >
                  前往创建
                </Button>
              </div>
            </div>

            <div className="density-toolbar density-toolbar--clean kb-toolbar-stack__row">
              <div className="density-toolbar__group">
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
                <Tooltip title="仅看重排开启">
                  <Button
                    shape="circle"
                    icon={<ThunderboltOutlined />}
                    onClick={() => {
                      setOnlyRerankEnabled((prev) => !prev);
                    }}
                    type={onlyRerankEnabled ? "primary" : "default"}
                    aria-label="仅看重排开启"
                  />
                </Tooltip>
              </div>
              <div className="density-toolbar__group density-toolbar__group--meta">
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
              </div>
            </div>
          </div>
          {kbQuery.isError ? <RequestErrorAlert error={normalizeApiError(kbQuery.error)} /> : null}
          <PageState status={status}>
            <div className="ops-scroll-pane">
              <Table
                size={tableDensity}
                className={`admin-table--priority kb-table${
                  tableDensity === "small" ? " dense-table" : ""
                }`}
                rowKey="kb_id"
                tableLayout="fixed"
                dataSource={filteredItems}
                pagination={false}
                scroll={{ x: 980 }}
                columns={[
                  {
                    title: "知识库",
                    dataIndex: "name",
                    width: 320,
                    fixed: "left",
                    className: "admin-table-cell--primary",
                    render: (_value: string, record) => (
                      <div className="kb-name-cell">
                        <Typography.Text
                          strong
                          ellipsis={{ tooltip: record.name }}
                          className="kb-name-cell__title"
                        >
                          {record.name}
                        </Typography.Text>
                        <Typography.Paragraph
                          type="secondary"
                          ellipsis={{ rows: 2, tooltip: record.description || "暂无说明" }}
                          className="kb-name-cell__desc"
                        >
                          {record.description || "暂无说明"}
                        </Typography.Paragraph>
                      </div>
                    )
                  },
                  {
                    title: "策略",
                    key: "retrieval",
                    width: 190,
                    className: "admin-table-cell--meta",
                    render: (_, record) => (
                      <div className="kb-strategy-cell">
                        <Typography.Text className="kb-strategy-cell__primary">
                          TopK {record.config?.topk ?? "-"} · 阈值 {record.config?.threshold ?? "-"}
                        </Typography.Text>
                        <Typography.Text type="secondary" className="kb-strategy-cell__secondary">
                          重排 {record.config?.rerank_enabled ? "on" : "off"} · 上下文{" "}
                          {record.config?.max_context_tokens ?? "-"}
                        </Typography.Text>
                      </div>
                    )
                  },
                  {
                    title: "可见性",
                    dataIndex: "visibility",
                    width: 108,
                    className: "admin-table-cell--status",
                    render: (value: KbEditValues["visibility"]) => (
                      <Tag color={resolveVisibilityColor(value)} icon={<EyeOutlined />}>
                        {value}
                      </Tag>
                    )
                  },
                  {
                    title: "更新时间",
                    dataIndex: "updated_at",
                    width: 150,
                    className: "admin-table-cell--time",
                    render: (value: string) => {
                      const formatted = formatDateParts(value);
                      return (
                        <div className="kb-updated-cell">
                          <Typography.Text type="secondary">{formatted.date}</Typography.Text>
                          {formatted.time ? (
                            <Typography.Text type="secondary" className="kb-updated-cell__time">
                              {formatted.time}
                            </Typography.Text>
                          ) : null}
                        </div>
                      );
                    }
                  },
                  {
                    title: "操作",
                    key: "actions",
                    width: 96,
                    fixed: "right",
                    className: "admin-table-cell--actions",
                    render: (_, record: { kb_id: string }) => (
                      <Space size={8} className="kb-actions">
                        <Tooltip title="编辑">
                          <Button
                            size="small"
                            shape="circle"
                            icon={<EditOutlined />}
                            onClick={() => {
                              setEditingKbId(record.kb_id);
                            }}
                            aria-label="编辑知识库"
                          />
                        </Tooltip>
                        <ConfirmAction
                          title="确认删除该知识库？"
                          okText="确认删除"
                          cancelText="取消"
                          onConfirm={() => deleteMutation.mutate(record.kb_id)}
                          buttonText=""
                          icon={<DeleteOutlined />}
                          danger
                          size="small"
                          shape="circle"
                          loading={deleteMutation.isPending}
                          ariaLabel="删除知识库"
                        />
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
        className="kb-edit-modal"
        width={680}
        title={
          <Space size={8}>
            <SettingOutlined />
            <span>编辑知识库</span>
          </Space>
        }
        open={Boolean(editingKbId)}
        onCancel={() => setEditingKbId(null)}
        confirmLoading={updateMutation.isPending}
        okText="保存变更"
        cancelText="取消"
        onOk={() => {
          void editForm.submit();
        }}
      >
        {kbDetailQuery.isError ? <RequestErrorAlert error={normalizeApiError(kbDetailQuery.error)} /> : null}
        <div className="kb-modal-copy">
          <Typography.Text className="kb-pane-copy__title">
            {kbDetailQuery.data?.name ?? "当前知识库"}
          </Typography.Text>
          <Typography.Text className="kb-pane-copy__desc">
            只保留说明、可见性和关键检索参数，避免弹窗承载过多次要信息。
          </Typography.Text>
        </div>
        <Form<KbEditValues>
          form={editForm}
          layout="vertical"
          onFinish={(values) => updateMutation.mutate(values)}
        >
          <Form.Item name="description" label="知识库说明">
            <Input.TextArea rows={2} />
          </Form.Item>
          <div className="kb-form-section kb-form-section--modal">
            <div className="kb-form-section__head">
              <Typography.Text className="kb-form-section__title">访问与策略</Typography.Text>
              <Typography.Text className="kb-form-section__hint">
                使用更轻的单栏布局，保证每个参数都有稳定阅读节奏。
              </Typography.Text>
            </div>
            <div className="kb-modal-grid">
              <Form.Item name="visibility" label="可见性" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: "public", label: "public" },
                    { value: "internal", label: "internal" },
                    { value: "admin", label: "admin" }
                  ]}
                />
              </Form.Item>
              <Form.Item name="topk" label="TopK">
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="threshold" label="阈值">
                <InputNumber min={0} max={1} step={0.01} style={{ width: "100%" }} />
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
                <InputNumber min={100} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="min_context_chars" label="最小上下文长度">
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="min_keyword_coverage" label="最小关键词覆盖率">
                <InputNumber min={0} max={1} step={0.05} style={{ width: "100%" }} />
              </Form.Item>
            </div>
          </div>
        </Form>
      </Modal>
    </div>
  );
}
