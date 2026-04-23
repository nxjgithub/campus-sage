import { useEffect, useMemo, useState } from "react";
import {
  ArrowRightOutlined,
  BarChartOutlined,
  ReloadOutlined,
  RocketOutlined,
  SearchOutlined,
  SettingOutlined
} from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button, Card, Empty, Form, InputNumber, Segmented, Select, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import { useNavigate, useSearchParams } from "react-router-dom";
import { EvalRunResponse, fetchEvalRun, runEval } from "../../shared/api/modules/eval";
import { fetchKbList } from "../../shared/api/modules/kb";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { CompactPageHero } from "../../shared/components/CompactPageHero";
import { MetricBarChart } from "../../shared/components/MetricCharts";
import { OpsPane } from "../../shared/components/OpsWorkbench";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import {
  EvalRunFormValues,
  FetchRunFormValues,
  formatDateTime,
  formatMetric,
  pushRecentEvalRun,
  readRecentEvalRuns,
  readRecentEvalSets,
  RecentEvalRunOption,
  RecentEvalSetOption,
  TableDensity
} from "./evalShared";

export function EvalPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [runForm] = Form.useForm<EvalRunFormValues>();
  const [fetchRunForm] = Form.useForm<FetchRunFormValues>();
  const [recentSets] = useState<RecentEvalSetOption[]>(() => readRecentEvalSets());
  const [recentRuns, setRecentRuns] = useState<RecentEvalRunOption[]>(() => readRecentEvalRuns());
  const [selectedRunId, setSelectedRunId] = useState<string | undefined>(
    () => searchParams.get("runId") ?? undefined
  );
  const [runDetail, setRunDetail] = useState<EvalRunResponse | null>(null);
  const [tableDensity, setTableDensity] = useState<TableDensity>("small");

  const prefilledEvalSetId = searchParams.get("evalSetId") ?? undefined;
  const prefilledRunId = searchParams.get("runId") ?? undefined;

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList
  });

  useEffect(() => {
    if (prefilledEvalSetId) {
      runForm.setFieldValue("eval_set_id", prefilledEvalSetId);
    }
  }, [prefilledEvalSetId, runForm]);

  useEffect(() => {
    if (prefilledRunId) {
      fetchRunForm.setFieldValue("run_id", prefilledRunId);
      setSelectedRunId(prefilledRunId);
    }
  }, [fetchRunForm, prefilledRunId]);

  const updateSearchParams = (updates: Record<string, string | undefined>) => {
    const nextParams = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value) {
        nextParams.set(key, value);
      } else {
        nextParams.delete(key);
      }
    });
    setSearchParams(nextParams, { replace: true });
  };

  const runEvalMutation = useMutation({
    mutationFn: runEval,
    onSuccess: (data) => {
      message.success("评测运行完成");
      setRunDetail(data);
      const nextRecentRuns = pushRecentEvalRun({
        run_id: data.run_id,
        eval_set_id: data.eval_set_id,
        kb_id: data.kb_id,
        created_at: data.created_at
      });
      setRecentRuns(nextRecentRuns);
      fetchRunForm.setFieldValue("run_id", data.run_id);
      setSelectedRunId(data.run_id);
      updateSearchParams({
        evalSetId: data.eval_set_id,
        runId: data.run_id
      });
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
      const nextRecentRuns = pushRecentEvalRun({
        run_id: data.run_id,
        eval_set_id: data.eval_set_id,
        kb_id: data.kb_id,
        created_at: data.created_at
      });
      setRecentRuns(nextRecentRuns);
      setSelectedRunId(data.run_id);
      updateSearchParams({
        evalSetId: data.eval_set_id,
        runId: data.run_id
      });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const firstError = useMemo(() => {
    if (kbQuery.isError) return normalizeApiError(kbQuery.error);
    if (runEvalMutation.isError) return normalizeApiError(runEvalMutation.error);
    if (fetchRunMutation.isError) return normalizeApiError(fetchRunMutation.error);
    return null;
  }, [
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
  const qualityMetricItems = [
    {
      key: "recall",
      label: "Recall@K",
      value: metrics?.recall_at_k ?? 0,
      color: "#2563eb"
    },
    {
      key: "mrr",
      label: "MRR",
      value: metrics?.mrr ?? 0,
      color: "#0ea5a0"
    }
  ];
  const latencyMetricItems = [
    {
      key: "avg_ms",
      label: "平均耗时",
      value: metrics?.avg_ms ?? 0,
      color: "#f59e0b"
    },
    {
      key: "p95_ms",
      label: "P95",
      value: metrics?.p95_ms ?? 0,
      color: "#dc2626"
    }
  ];

  return (
    <div className="page-stack">
      {firstError ? <RequestErrorAlert error={firstError} /> : null}

      <CompactPageHero
        kicker="离线评测"
        title="离线评测中心"
        description="当前页面只负责运行参数与结果查看；评测集设计已拆到独立页面，避免样本录入和结果分析同屏拥挤。"
        stats={[
          { label: "评测集", value: recentSets.length },
          { label: "运行", value: recentRuns.length },
          { label: "Recall@K", value: formatMetric(metrics?.recall_at_k) },
          { label: "P95", value: formatMetric(metrics?.p95_ms) }
        ]}
      />

      <div className="dashboard-grid">
        <Card className="card-soft" size="small" title="质量指标">
          <MetricBarChart
            items={qualityMetricItems}
            emptyText="完成一次评测后显示质量指标"
            valueFormatter={(value) => value.toFixed(3)}
          />
        </Card>
        <Card className="card-soft" size="small" title="时延指标">
          <MetricBarChart
            items={latencyMetricItems}
            emptyText="完成一次评测后显示时延指标"
            valueFormatter={(value) => `${value.toFixed(1)} ms`}
          />
        </Card>
      </div>

      <Card className="card-soft split-manage-card">
        <OpsPane
          title={
            <Space size={8}>
              <BarChartOutlined />
              <span>运行与结果</span>
            </Space>
          }
          toolbar={
            <div className="density-toolbar density-toolbar--clean">
              <div className="density-toolbar__group">
                <Typography.Text className="density-meta">
                  评测集缓存 {recentSets.length}，运行缓存 {recentRuns.length}
                </Typography.Text>
              </div>
              <div className="density-toolbar__group density-toolbar__group--meta">
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
                <Button
                  type="primary"
                  icon={<ArrowRightOutlined />}
                  onClick={() => {
                    navigate("/admin/eval/create");
                  }}
                >
                  前往创建
                </Button>
              </div>
            </div>
          }
        >
          <div className="split-pane-copy split-pane-copy--compact">
            <Typography.Text className="split-pane-copy__title">
              样本设计已拆分，当前页只保留运行链路
            </Typography.Text>
            <Typography.Text className="split-pane-copy__desc">
              这里专注选择评测集、知识库和运行参数，再统一回看指标结果与历史运行。
            </Typography.Text>
          </div>

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
                  请先进入独立创建页录入评测集，再回到这里发起运行。
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
              <div className="split-actions">
                <Button
                  onClick={() => {
                    navigate("/admin/eval/create");
                  }}
                >
                  去创建评测集
                </Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<RocketOutlined />}
                  loading={runEvalMutation.isPending}
                >
                  开始评测
                </Button>
              </div>
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
              <Tooltip title="刷新当前评测结果">
                <Button
                  size="small"
                  shape="circle"
                  icon={<ReloadOutlined />}
                  onClick={() => {
                    if (selectedRunId) {
                      fetchRunMutation.mutate(selectedRunId);
                    }
                  }}
                  disabled={!selectedRunId}
                  loading={fetchRunMutation.isPending}
                  aria-label="刷新当前评测结果"
                />
              </Tooltip>
            }
            style={{ marginTop: 12 }}
          >
            <Form<FetchRunFormValues>
              form={fetchRunForm}
              layout="inline"
              onValuesChange={(_, values) => {
                setSelectedRunId(values.run_id);
              }}
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
                <Tooltip title="查询">
                  <Button
                    htmlType="submit"
                    shape="circle"
                    icon={<SearchOutlined />}
                    loading={fetchRunMutation.isPending}
                    disabled={!recentRuns.length}
                    aria-label="查询评测结果"
                  />
                </Tooltip>
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
                  className={`admin-table--priority${
                    tableDensity === "small" ? " dense-table" : ""
                  }`}
                  rowKey="metric"
                  tableLayout="fixed"
                  pagination={false}
                  scroll={{ x: 460 }}
                  dataSource={[
                    { metric: "Recall@K", value: formatMetric(runDetail.metrics?.recall_at_k) },
                    { metric: "MRR", value: formatMetric(runDetail.metrics?.mrr) },
                    { metric: "平均耗时(ms)", value: formatMetric(runDetail.metrics?.avg_ms) },
                    { metric: "P95(ms)", value: formatMetric(runDetail.metrics?.p95_ms) },
                    { metric: "样本数", value: formatMetric(runDetail.metrics?.samples) }
                  ]}
                  columns={[
                    {
                      title: "指标",
                      dataIndex: "metric",
                      width: 240,
                      fixed: "left",
                      className: "admin-table-cell--primary"
                    },
                    {
                      title: "值",
                      dataIndex: "value",
                      width: 180,
                      align: "right",
                      className: "admin-table-cell--number"
                    }
                  ]}
                />
              </Space>
            )}
          </Card>
        </OpsPane>
      </Card>
    </div>
  );
}
