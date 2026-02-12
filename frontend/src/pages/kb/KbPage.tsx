import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
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
import { normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
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

export function KbPage() {
  const queryClient = useQueryClient();
  const [createForm] = Form.useForm<KbFormValues>();
  const [editForm] = Form.useForm<KbEditValues>();
  const [editingKbId, setEditingKbId] = useState<string | null>(null);

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
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  const updateMutation = useMutation({
    mutationFn: async (values: KbEditValues) => {
      if (!editingKbId) {
        throw new Error("缺少知识库 ID");
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
      message.error(`${normalized.message}（${normalized.code}）`);
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
      message.error(`${normalized.message}（${normalized.code}）`);
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
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Typography.Title level={4} className="hero-title">
            知识库配置中心
          </Typography.Title>
          <Typography.Text className="hero-desc">
            统一维护 KB 基础信息、可见性策略和检索参数，保证问答行为可控与可追踪。
          </Typography.Text>
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
        </Space>
      </Card>

      <Card title="创建知识库" className="card-soft">
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
          </Card>
          <Form.Item style={{ marginTop: 12 }}>
            <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
              创建
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card
        title="知识库列表"
        className="card-soft"
        extra={
          <Button onClick={() => void kbQuery.refetch()} loading={kbQuery.isFetching}>
            刷新
          </Button>
        }
      >
        {kbQuery.isError ? <RequestErrorAlert error={normalizeApiError(kbQuery.error)} /> : null}
        <PageState status={status}>
          <Table
            rowKey="kb_id"
            dataSource={kbQuery.data?.items ?? []}
            pagination={false}
            columns={[
              { title: "知识库ID", dataIndex: "kb_id", width: 280 },
              { title: "名称", dataIndex: "name" },
              {
                title: "可见性",
                dataIndex: "visibility",
                width: 120,
                render: (value: string) => <Tag>{value}</Tag>
              },
              { title: "更新时间", dataIndex: "updated_at", width: 220 },
              {
                title: "操作",
                key: "actions",
                width: 220,
                render: (_, record: { kb_id: string }) => (
                  <Space>
                    <Button
                      size="small"
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
                      danger
                      size="small"
                      loading={deleteMutation.isPending}
                    />
                  </Space>
                )
              }
            ]}
          />
        </PageState>
      </Card>

      <Modal
        title="编辑知识库"
        open={Boolean(editingKbId)}
        onCancel={() => setEditingKbId(null)}
        confirmLoading={updateMutation.isPending}
        onOk={() => {
          void editForm.submit();
        }}
      >
        {kbDetailQuery.isError ? (
          <RequestErrorAlert error={normalizeApiError(kbDetailQuery.error)} />
        ) : null}
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
