import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message
} from "antd";
import { fetchKbList } from "../../shared/api/modules/kb";
import { createEvalSet, EvalRunResponse, fetchEvalRun, runEval } from "../../shared/api/modules/eval";
import { normalizeApiError } from "../../shared/api/errors";
import { CopyableField } from "../../shared/components/CopyableField";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";

interface EvalItemFormRow {
  question: string;
  gold_doc_id?: string;
  gold_page_start?: number;
  gold_page_end?: number;
  tags_text?: string;
}

interface EvalSetFormValues {
  name: string;
  description?: string;
  items: EvalItemFormRow[];
}

interface EvalRunFormValues {
  eval_set_id: string;
  kb_id: string;
  topk: number;
  threshold?: number;
  rerank_enabled?: boolean;
}

interface FetchRunFormValues {
  run_id: string;
}
type TableDensity = "middle" | "small";

function parseTags(value?: string) {
  if (!value) {
    return undefined;
  }
  const tags = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return tags.length ? tags : undefined;
}

export function EvalPage() {
  const [setForm] = Form.useForm<EvalSetFormValues>();
  const [runForm] = Form.useForm<EvalRunFormValues>();
  const [fetchRunForm] = Form.useForm<FetchRunFormValues>();
  const [recentSetIds, setRecentSetIds] = useState<string[]>([]);
  const [recentRunIds, setRecentRunIds] = useState<string[]>([]);
  const [runDetail, setRunDetail] = useState<EvalRunResponse | null>(null);
  const [tableDensity, setTableDensity] = useState<TableDensity>("small");

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList
  });

  const createSetMutation = useMutation({
    mutationFn: async (values: EvalSetFormValues) =>
      createEvalSet({
        name: values.name.trim(),
        description: values.description?.trim() || undefined,
        items: values.items.map((item) => ({
          question: item.question.trim(),
          gold_doc_id: item.gold_doc_id?.trim() || undefined,
          gold_page_start: item.gold_page_start,
          gold_page_end: item.gold_page_end,
          tags: parseTags(item.tags_text)
        }))
      }),
    onSuccess: (data) => {
      message.success("评测集创建成功");
      setRecentSetIds((prev) => [data.eval_set_id, ...prev.filter((id) => id !== data.eval_set_id)].slice(0, 10));
      runForm.setFieldValue("eval_set_id", data.eval_set_id);
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  const runEvalMutation = useMutation({
    mutationFn: runEval,
    onSuccess: (data) => {
      message.success("评测运行完成");
      setRunDetail(data);
      setRecentRunIds((prev) => [data.run_id, ...prev.filter((id) => id !== data.run_id)].slice(0, 10));
      fetchRunForm.setFieldValue("run_id", data.run_id);
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  const fetchRunMutation = useMutation({
    mutationFn: fetchEvalRun,
    onSuccess: (data) => {
      setRunDetail(data);
      message.success("评测结果已加载");
      setRecentRunIds((prev) => [data.run_id, ...prev.filter((id) => id !== data.run_id)].slice(0, 10));
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  const firstError = useMemo(() => {
    if (kbQuery.isError) return normalizeApiError(kbQuery.error);
    if (createSetMutation.isError) return normalizeApiError(createSetMutation.error);
    if (runEvalMutation.isError) return normalizeApiError(runEvalMutation.error);
    if (fetchRunMutation.isError) return normalizeApiError(fetchRunMutation.error);
    return null;
  }, [
    createSetMutation.error,
    createSetMutation.isError,
    fetchRunMutation.error,
    fetchRunMutation.isError,
    kbQuery.error,
    kbQuery.isError,
    runEvalMutation.error,
    runEvalMutation.isError
  ]);

  const metrics = runDetail?.metrics ?? null;

  return (
    <div className="page-stack">
      {firstError ? <RequestErrorAlert error={firstError} /> : null}

      <Card className="hero-card">
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Typography.Title level={4} className="hero-title">
            离线评测中心
          </Typography.Title>
          <Typography.Text className="hero-desc">
            统一管理评测样本、运行参数与指标结果，服务检索质量迭代。
          </Typography.Text>
          <div className="summary-grid">
            <div className="summary-item">
              <div className="summary-item-label">最近评测集</div>
              <div className="summary-item-value">{recentSetIds.length}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">最近运行</div>
              <div className="summary-item-value">{recentRunIds.length}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">Recall@K</div>
              <div className="summary-item-value">{metrics?.recall_at_k ?? "-"}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">MRR</div>
              <div className="summary-item-value">{metrics?.mrr ?? "-"}</div>
            </div>
          </div>
        </Space>
      </Card>

      <div className="ops-workbench">
        <Card title="创建评测集" className="card-soft ops-pane-card">
          <div className="ops-pane-body">
            <div className="ops-scroll-pane">
              <Form<EvalSetFormValues>
                form={setForm}
                layout="vertical"
                initialValues={{
                  items: [{ question: "", gold_doc_id: "", tags_text: "" }]
                }}
                onFinish={(values) => {
                  createSetMutation.mutate(values);
                }}
              >
                <Form.Item
                  name="name"
                  label="评测集名称"
                  rules={[{ required: true, message: "请输入名称" }]}
                >
                  <Input placeholder="例如：教务评测集_v1" />
                </Form.Item>
                <Form.Item name="description" label="描述（可选）">
                  <Input.TextArea rows={2} />
                </Form.Item>
                <Form.List name="items">
                  {(fields, { add, remove }) => (
                    <Space direction="vertical" style={{ width: "100%" }}>
                      {fields.map((field, index) => (
                        <Card key={field.key} size="small" title={`样本 ${index + 1}`} className="card-inset">
                          <Form.Item
                            name={[field.name, "question"]}
                            label="问题"
                            rules={[{ required: true, message: "请输入问题" }]}
                          >
                            <Input.TextArea rows={2} />
                          </Form.Item>
                          <Space wrap>
                            <Form.Item name={[field.name, "gold_doc_id"]} label="标准文档ID">
                              <Input style={{ width: 220 }} />
                            </Form.Item>
                            <Form.Item name={[field.name, "gold_page_start"]} label="起始页">
                              <InputNumber min={1} />
                            </Form.Item>
                            <Form.Item name={[field.name, "gold_page_end"]} label="结束页">
                              <InputNumber min={1} />
                            </Form.Item>
                            <Form.Item name={[field.name, "tags_text"]} label="标签（逗号分隔）">
                              <Input style={{ width: 260 }} placeholder="policy, exam" />
                            </Form.Item>
                          </Space>
                          <Button
                            danger
                            onClick={() => {
                              remove(field.name);
                            }}
                            disabled={fields.length <= 1}
                          >
                            删除样本
                          </Button>
                        </Card>
                      ))}
                      <Space>
                        <Button
                          onClick={() => {
                            add({ question: "", gold_doc_id: "", tags_text: "" });
                          }}
                        >
                          新增样本
                        </Button>
                        <Button type="primary" htmlType="submit" loading={createSetMutation.isPending}>
                          创建评测集
                        </Button>
                      </Space>
                    </Space>
                  )}
                </Form.List>
              </Form>
            </div>
          </div>
        </Card>

        <Card title="运行与结果" className="card-soft ops-pane-card">
          <div className="ops-pane-body">
            <div className="ops-scroll-pane">
              <div className="density-toolbar">
                <Typography.Text className="density-meta">
                  评测集缓存 {recentSetIds.length}，运行缓存 {recentRunIds.length}
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
              <Card size="small" className="card-inset" title="运行评测">
                <Form<EvalRunFormValues>
                  form={runForm}
                  layout="vertical"
                  initialValues={{ topk: 5 }}
                  onFinish={(values) => {
                    runEvalMutation.mutate(values);
                  }}
                >
                  <Form.Item
                    name="eval_set_id"
                    label="评测集ID"
                    rules={[{ required: true, message: "请输入评测集ID" }]}
                  >
                    <Select
                      showSearch
                      placeholder="输入或选择评测集ID"
                      options={recentSetIds.map((id) => ({ value: id, label: id }))}
                    />
                  </Form.Item>
                  <Form.Item
                    name="kb_id"
                    label="知识库"
                    rules={[{ required: true, message: "请选择知识库" }]}
                  >
                    <Select
                      loading={kbQuery.isLoading}
                      options={(kbQuery.data?.items ?? []).map((item) => ({
                        value: item.kb_id,
                        label: `${item.name} (${item.kb_id})`
                      }))}
                    />
                  </Form.Item>
                  <Space wrap>
                    <Form.Item name="topk" label="TopK">
                      <InputNumber min={1} />
                    </Form.Item>
                    <Form.Item name="threshold" label="阈值（可选）">
                      <InputNumber min={0} max={1} step={0.01} />
                    </Form.Item>
                    <Form.Item name="rerank_enabled" label="重排（可选）">
                      <Select
                        allowClear
                        style={{ width: 160 }}
                        options={[
                          { value: true, label: "true" },
                          { value: false, label: "false" }
                        ]}
                      />
                    </Form.Item>
                  </Space>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={runEvalMutation.isPending}>
                      开始评测
                    </Button>
                  </Form.Item>
                </Form>
              </Card>

              <Card size="small" title="查询评测结果" style={{ marginTop: 12 }}>
                <Form<FetchRunFormValues>
                  form={fetchRunForm}
                  layout="inline"
                  onFinish={(values) => {
                    fetchRunMutation.mutate(values.run_id);
                  }}
                >
                  <Form.Item
                    name="run_id"
                    rules={[{ required: true, message: "请输入运行ID" }]}
                    style={{ width: 320 }}
                  >
                    <Select
                      showSearch
                      placeholder="输入或选择运行ID"
                      options={recentRunIds.map((id) => ({ value: id, label: id }))}
                    />
                  </Form.Item>
                  <Form.Item>
                    <Button htmlType="submit" loading={fetchRunMutation.isPending}>
                      查询
                    </Button>
                  </Form.Item>
                </Form>

                {!runDetail ? (
                  <Typography.Text type="secondary">暂无评测结果。</Typography.Text>
                ) : (
                  <Space direction="vertical" style={{ width: "100%", marginTop: 12 }}>
                    <CopyableField label="run_id" value={runDetail.run_id} />
                    <CopyableField label="eval_set_id" value={runDetail.eval_set_id} />
                    <CopyableField label="kb_id" value={runDetail.kb_id} />
                    <CopyableField label="request_id" value={runDetail.request_id} />
                    <Space wrap>
                      <Tag>topk: {runDetail.topk}</Tag>
                      <Tag>threshold: {runDetail.threshold ?? "-"}</Tag>
                      <Tag>rerank: {String(runDetail.rerank_enabled)}</Tag>
                    </Space>
                    <Table
                      size={tableDensity}
                      className={tableDensity === "small" ? "dense-table" : undefined}
                      rowKey="metric"
                      pagination={false}
                      dataSource={[
                        { metric: "recall_at_k", value: runDetail.metrics?.recall_at_k ?? "-" },
                        { metric: "mrr", value: runDetail.metrics?.mrr ?? "-" },
                        { metric: "avg_ms", value: runDetail.metrics?.avg_ms ?? "-" },
                        { metric: "p95_ms", value: runDetail.metrics?.p95_ms ?? "-" },
                        { metric: "samples", value: runDetail.metrics?.samples ?? "-" }
                      ]}
                      columns={[
                        { title: "指标", dataIndex: "metric", width: 180 },
                        { title: "值", dataIndex: "value" }
                      ]}
                    />
                  </Space>
                )}
              </Card>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
