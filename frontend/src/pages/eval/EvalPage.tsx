import { useMemo, useState } from "react";
import {
  BarChartOutlined,
  DatabaseOutlined,
  PlusOutlined,
  ReloadOutlined,
  RocketOutlined,
  SearchOutlined,
  SettingOutlined,
  TagsOutlined
} from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  Empty,
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
import { createEvalSet, EvalRunResponse, fetchEvalRun, runEval } from "../../shared/api/modules/eval";
import { fetchKbList } from "../../shared/api/modules/kb";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { OpsPane, OpsWorkbench } from "../../shared/components/OpsWorkbench";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";

interface EvalItemFormRow {
  question: string;
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

interface RecentEvalSetOption {
  eval_set_id: string;
  name: string;
  created_at: string;
}

interface RecentEvalRunOption {
  run_id: string;
  eval_set_id: string;
  kb_id: string;
  created_at: string;
}

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

function formatDateTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function formatMetric(value?: number | null) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(3);
}

export function EvalPage() {
  const [setForm] = Form.useForm<EvalSetFormValues>();
  const [runForm] = Form.useForm<EvalRunFormValues>();
  const [fetchRunForm] = Form.useForm<FetchRunFormValues>();
  const [recentSets, setRecentSets] = useState<RecentEvalSetOption[]>([]);
  const [recentRuns, setRecentRuns] = useState<RecentEvalRunOption[]>([]);
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
          gold_page_start: item.gold_page_start,
          gold_page_end: item.gold_page_end,
          tags: parseTags(item.tags_text)
        }))
      }),
    onSuccess: (data) => {
      message.success("评测集创建成功");
      setRecentSets((previous) =>
        [
          {
            eval_set_id: data.eval_set_id,
            name: data.name,
            created_at: data.created_at
          },
          ...previous.filter((item) => item.eval_set_id !== data.eval_set_id)
        ].slice(0, 10)
      );
      runForm.setFieldValue("eval_set_id", data.eval_set_id);
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const runEvalMutation = useMutation({
    mutationFn: runEval,
    onSuccess: (data) => {
      message.success("评测运行完成");
      setRunDetail(data);
      setRecentRuns((previous) =>
        [
          {
            run_id: data.run_id,
            eval_set_id: data.eval_set_id,
            kb_id: data.kb_id,
            created_at: data.created_at
          },
          ...previous.filter((item) => item.run_id !== data.run_id)
        ].slice(0, 10)
      );
      fetchRunForm.setFieldValue("run_id", data.run_id);
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const fetchRunMutation = useMutation({
    mutationFn: fetchEvalRun,
    onSuccess: (data) => {
      setRunDetail(data);
      message.success("评测结果已加载");
      setRecentRuns((previous) =>
        [
          {
            run_id: data.run_id,
            eval_set_id: data.eval_set_id,
            kb_id: data.kb_id,
            created_at: data.created_at
          },
          ...previous.filter((item) => item.run_id !== data.run_id)
        ].slice(0, 10)
      );
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
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
  const kbNameMap = useMemo(
    () => new Map((kbQuery.data?.items ?? []).map((item) => [item.kb_id, item.name])),
    [kbQuery.data?.items]
  );
  const evalSetNameMap = useMemo(
    () => new Map(recentSets.map((item) => [item.eval_set_id, item.name])),
    [recentSets]
  );

  return (
    <div className="page-stack">
      {firstError ? <RequestErrorAlert error={firstError} /> : null}

      <Card className="hero-card">
        <div className="hero-layout">
          <Space direction="vertical" size={10} style={{ width: "100%" }}>
            <span className="hero-kicker">Eval Center</span>
            <Typography.Title level={4} className="hero-title">
              离线评测中心
            </Typography.Title>
            <Typography.Text className="hero-desc">
              统一管理评测样本、运行参数与指标结果，减少管理端“先记 ID 再查询”的割裂感。
            </Typography.Text>
            <div className="hero-note">
              <span className="hero-note__item">样本创建与运行放在同一工作台</span>
              <span className="hero-note__item">评测结果直接回填右侧结果区</span>
              <span className="hero-note__item">操作入口改为图标 + 短文案</span>
            </div>
          </Space>
          <div className="summary-grid">
            <div className="summary-item">
              <div className="summary-item-label">最近评测集</div>
              <div className="summary-item-value">{recentSets.length}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">最近运行</div>
              <div className="summary-item-value">{recentRuns.length}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">Recall@K</div>
              <div className="summary-item-value">{formatMetric(metrics?.recall_at_k)}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">P95 延迟</div>
              <div className="summary-item-value">{formatMetric(metrics?.p95_ms)}</div>
            </div>
          </div>
        </div>
      </Card>

      <OpsWorkbench
        left={
          <OpsPane
            title={
              <Space size={8}>
                <DatabaseOutlined />
                <span>评测集设计</span>
              </Space>
            }
            introTitle="先组织样本，再发起离线评测"
            introDescription="每条样本至少填写问题，可补充页码和标签。创建成功后会自动进入右侧运行面板的评测集选择器。"
          >
              <Form<EvalSetFormValues>
                form={setForm}
                layout="vertical"
                initialValues={{
                  items: [{ question: "", tags_text: "" }]
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
                  <Input placeholder="例如：教务问答评测集_v2" />
                </Form.Item>
                <Form.Item name="description" label="描述（可选）">
                  <Input.TextArea rows={3} placeholder="说明样本范围、目标场景或评测目的" />
                </Form.Item>

                <Form.List name="items">
                  {(fields, { add, remove }) => (
                    <Space direction="vertical" style={{ width: "100%" }} size={12}>
                      {fields.map((field, index) => (
                        <Card
                          key={field.key}
                          size="small"
                          className="card-inset"
                          title={`样本 ${index + 1}`}
                          extra={
                            <Button
                              danger
                              size="small"
                              onClick={() => {
                                remove(field.name);
                              }}
                              disabled={fields.length <= 1}
                            >
                              删除
                            </Button>
                          }
                        >
                          <Form.Item
                            name={[field.name, "question"]}
                            label="问题"
                            rules={[{ required: true, message: "请输入问题" }]}
                          >
                            <Input.TextArea rows={3} placeholder="输入用于评测的问题" />
                          </Form.Item>
                          <div className="ops-kpi-grid">
                            <Form.Item name={[field.name, "gold_page_start"]} label="起始页">
                              <InputNumber min={1} style={{ width: "100%" }} />
                            </Form.Item>
                            <Form.Item name={[field.name, "gold_page_end"]} label="结束页">
                              <InputNumber min={1} style={{ width: "100%" }} />
                            </Form.Item>
                            <Form.Item name={[field.name, "tags_text"]} label="标签（逗号分隔）">
                              <Input placeholder="policy, exam" prefix={<TagsOutlined />} />
                            </Form.Item>
                          </div>
                        </Card>
                      ))}

                      <Space wrap>
                        <Button
                          icon={<PlusOutlined />}
                          onClick={() => {
                            add({ question: "", tags_text: "" });
                          }}
                        >
                          新增样本
                        </Button>
                        <Button
                          type="primary"
                          htmlType="submit"
                          icon={<DatabaseOutlined />}
                          loading={createSetMutation.isPending}
                        >
                          创建评测集
                        </Button>
                      </Space>
                    </Space>
                  )}
                </Form.List>
              </Form>
          </OpsPane>
        }
        right={
          <OpsPane
            title={
              <Space size={8}>
                <BarChartOutlined />
                <span>运行与结果</span>
              </Space>
            }
            toolbar={
              <div className="density-toolbar">
              <Typography.Text className="density-meta">
                评测集缓存 {recentSets.length}，运行缓存 {recentRuns.length}
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
            }
          >
              <Card
                size="small"
                className="card-inset"
                title={
                  <Space size={8}>
                    <RocketOutlined />
                    <span>发起评测</span>
                  </Space>
                }
              >
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
                    label="评测集"
                    rules={[{ required: true, message: "请选择评测集" }]}
                  >
                    <Select
                      showSearch
                      optionFilterProp="label"
                      placeholder="选择最近创建的评测集"
                      options={recentSets.map((item) => ({
                        value: item.eval_set_id,
                        label: `${item.name} · ${formatDateTime(item.created_at)}`
                      }))}
                    />
                  </Form.Item>
                  {!recentSets.length ? (
                    <Typography.Paragraph type="secondary" style={{ marginTop: -8 }}>
                      请先在左侧创建评测集，再发起评测运行。
                    </Typography.Paragraph>
                  ) : null}
                  <Form.Item
                    name="kb_id"
                    label="知识库"
                    rules={[{ required: true, message: "请选择知识库" }]}
                  >
                    <Select
                      loading={kbQuery.isLoading}
                      placeholder="选择待评测的知识库"
                      options={(kbQuery.data?.items ?? []).map((item) => ({
                        value: item.kb_id,
                        label: item.name
                      }))}
                    />
                  </Form.Item>
                  <div className="ops-kpi-grid">
                    <Form.Item name="topk" label="TopK">
                      <InputNumber min={1} style={{ width: "100%" }} />
                    </Form.Item>
                    <Form.Item name="threshold" label="阈值（可选）">
                      <InputNumber min={0} max={1} step={0.01} style={{ width: "100%" }} />
                    </Form.Item>
                    <Form.Item name="rerank_enabled" label="重排（可选）">
                      <Select
                        allowClear
                        placeholder="使用默认配置"
                        options={[
                          { value: true, label: "开启" },
                          { value: false, label: "关闭" }
                        ]}
                      />
                    </Form.Item>
                  </div>
                  <Form.Item style={{ marginBottom: 0 }}>
                    <Button
                      type="primary"
                      htmlType="submit"
                      icon={<RocketOutlined />}
                      loading={runEvalMutation.isPending}
                    >
                      开始评测
                    </Button>
                  </Form.Item>
                </Form>
              </Card>

              <Card
                size="small"
                className="card-inset"
                title={
                  <Space size={8}>
                    <SettingOutlined />
                    <span>结果中心</span>
                  </Space>
                }
                extra={
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={() => {
                      const runId = fetchRunForm.getFieldValue("run_id");
                      if (runId) {
                        fetchRunMutation.mutate(runId);
                      }
                    }}
                    disabled={!fetchRunForm.getFieldValue("run_id")}
                    loading={fetchRunMutation.isPending}
                    aria-label="刷新当前评测结果"
                  >
                    刷新
                  </Button>
                }
                style={{ marginTop: 12 }}
              >
                <Form<FetchRunFormValues>
                  form={fetchRunForm}
                  layout="inline"
                  onFinish={(values) => {
                    fetchRunMutation.mutate(values.run_id);
                  }}
                >
                  <Form.Item
                    name="run_id"
                    rules={[{ required: true, message: "请选择评测运行" }]}
                    style={{ minWidth: 300, flex: 1 }}
                  >
                    <Select
                      showSearch
                      optionFilterProp="label"
                      placeholder="选择最近评测运行"
                      options={recentRuns.map((item) => ({
                        value: item.run_id,
                        label: `${evalSetNameMap.get(item.eval_set_id) ?? "评测运行"} · ${
                          kbNameMap.get(item.kb_id) ?? "未知知识库"
                        } · ${formatDateTime(item.created_at)}`
                      }))}
                    />
                  </Form.Item>
                  <Form.Item>
                    <Button
                      htmlType="submit"
                      icon={<SearchOutlined />}
                      loading={fetchRunMutation.isPending}
                      disabled={!recentRuns.length}
                    >
                      查询
                    </Button>
                  </Form.Item>
                </Form>

                {!recentRuns.length ? (
                  <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
                    暂无可查询的评测运行，请先执行一次评测。
                  </Typography.Paragraph>
                ) : null}

                {!runDetail ? (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一次评测运行后查看结果。" />
                ) : (
                  <Space direction="vertical" size={12} style={{ width: "100%", marginTop: 12 }}>
                    <div className="ops-kpi-grid">
                      <div className="ops-kpi-item">
                        <span className="ops-kpi-item__label">评测集</span>
                        <span className="ops-kpi-item__value">
                          {evalSetNameMap.get(runDetail.eval_set_id) ?? "最近评测集"}
                        </span>
                      </div>
                      <div className="ops-kpi-item">
                        <span className="ops-kpi-item__label">知识库</span>
                        <span className="ops-kpi-item__value">
                          {kbNameMap.get(runDetail.kb_id) ?? "未知知识库"}
                        </span>
                      </div>
                      <div className="ops-kpi-item">
                        <span className="ops-kpi-item__label">运行时间</span>
                        <span className="ops-kpi-item__value">{formatDateTime(runDetail.created_at)}</span>
                      </div>
                      <div className="ops-kpi-item">
                        <span className="ops-kpi-item__label">样本量</span>
                        <span className="ops-kpi-item__value">{formatMetric(runDetail.metrics?.samples)}</span>
                      </div>
                    </div>

                    <Space wrap>
                      <Tag color="blue">TopK {runDetail.topk}</Tag>
                      <Tag>阈值 {runDetail.threshold ?? "默认"}</Tag>
                      <Tag>重排 {runDetail.rerank_enabled ? "开启" : "关闭"}</Tag>
                    </Space>

                    <Table
                      size={tableDensity}
                      className={tableDensity === "small" ? "dense-table" : undefined}
                      rowKey="metric"
                      pagination={false}
                      dataSource={[
                        { metric: "Recall@K", value: formatMetric(runDetail.metrics?.recall_at_k) },
                        { metric: "MRR", value: formatMetric(runDetail.metrics?.mrr) },
                        { metric: "平均耗时(ms)", value: formatMetric(runDetail.metrics?.avg_ms) },
                        { metric: "P95(ms)", value: formatMetric(runDetail.metrics?.p95_ms) },
                        { metric: "样本数", value: formatMetric(runDetail.metrics?.samples) }
                      ]}
                      columns={[
                        { title: "指标", dataIndex: "metric", width: 180 },
                        { title: "值", dataIndex: "value" }
                      ]}
                    />
                  </Space>
                )}
              </Card>
          </OpsPane>
        }
      />
    </div>
  );
}
