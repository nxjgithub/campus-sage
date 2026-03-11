import { useEffect, useMemo, useState } from "react";
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  ReloadOutlined,
  RetweetOutlined,
  StopOutlined,
  SyncOutlined
} from "@ant-design/icons";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Empty, Segmented, Select, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  cancelIngestJob,
  deleteDocument,
  DocumentItem,
  fetchDocuments,
  fetchIngestJob,
  IngestJob,
  reindexDocument,
  retryIngestJob
} from "../../shared/api/modules/documents";
import { fetchKbList } from "../../shared/api/modules/kb";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
import { CompactPageHero } from "../../shared/components/CompactPageHero";
import {
  DonutMetricChart,
  MetricBarChart,
  MiniTrendChart,
  TrendDatum
} from "../../shared/components/MetricCharts";
import { OpsPane } from "../../shared/components/OpsWorkbench";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import {
  DOCUMENT_STATUS_META,
  DocumentStatusFilter,
  FINAL_JOB_STATUS,
  formatDateTime,
  getJobStageLabel,
  JOB_STAGE_ORDER,
  JOB_STATUS_META,
  pushJobHistoryId,
  readJobHistoryIds,
  TableDensity
} from "./documentsShared";

interface DocumentsPageProps {
  initialKbId?: string;
}

export function DocumentsPage({ initialKbId }: DocumentsPageProps) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobHistoryIds, setJobHistoryIds] = useState<string[]>([]);
  const [jobStageSnapshots, setJobStageSnapshots] = useState<TrendDatum[]>([]);
  const [jobVectorSnapshots, setJobVectorSnapshots] = useState<TrendDatum[]>([]);
  const [tableDensity, setTableDensity] = useState<TableDensity>("small");
  const [docStatusFilter, setDocStatusFilter] = useState<DocumentStatusFilter>("all");
  const kbId = searchParams.get("kb") ?? initialKbId;

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList
  });

  const documentsQuery = useQuery({
    queryKey: ["documents", kbId],
    queryFn: async () => fetchDocuments(kbId as string),
    enabled: Boolean(kbId)
  });

  const jobQuery = useQuery({
    queryKey: ["ingest-job", activeJobId],
    queryFn: async () => fetchIngestJob(activeJobId as string),
    enabled: Boolean(activeJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || FINAL_JOB_STATUS.has(status)) {
        return false;
      }
      return 2_000;
    }
  });

  useEffect(() => {
    if (!kbId) {
      setJobHistoryIds([]);
      setActiveJobId(null);
      setJobStageSnapshots([]);
      setJobVectorSnapshots([]);
      return;
    }
    const ids = readJobHistoryIds(kbId);
    setJobHistoryIds(ids);
    setActiveJobId(ids[0] ?? null);
  }, [kbId]);

  useEffect(() => {
    if (!jobQuery.data || !activeJobId) {
      return;
    }

    setJobStageSnapshots((previous) =>
      [...previous, {
        key: `stage-${previous.length + 1}`,
        label: `T${previous.length + 1}`,
        value: JOB_STAGE_ORDER[jobQuery.data.progress?.stage ?? "queued"] ?? 0
      }]
        .slice(-8)
        .map((item, index) => ({
          ...item,
          key: `stage-${index + 1}`,
          label: `T${index + 1}`
        }))
    );

    setJobVectorSnapshots((previous) =>
      [...previous, {
        key: `vector-${previous.length + 1}`,
        label: `T${previous.length + 1}`,
        value: jobQuery.data.progress?.vectors_upserted ?? 0
      }]
        .slice(-8)
        .map((item, index) => ({
          ...item,
          key: `vector-${index + 1}`,
          label: `T${index + 1}`
        }))
    );
  }, [activeJobId, jobQuery.data]);

  const pushHistoryJob = (jobId: string) => {
    if (!kbId) {
      return;
    }
    setJobHistoryIds(pushJobHistoryId(kbId, jobId));
  };

  const historyQueries = useQueries({
    queries: jobHistoryIds.map((jobId) => ({
      queryKey: ["ingest-job", "history", jobId],
      queryFn: async () => fetchIngestJob(jobId),
      refetchInterval: (query: { state: { data?: { status?: string } } }) => {
        const status = query.state.data?.status;
        if (!status || FINAL_JOB_STATUS.has(status)) {
          return false;
        }
        return 4_000;
      }
    }))
  });

  const historyJobs = useMemo(
    () =>
      historyQueries
        .map((query) => query.data)
        .filter((item): item is NonNullable<typeof item> => Boolean(item)),
    [historyQueries]
  );

  const deleteMutation = useMutation({
    mutationFn: async (docId: string) => deleteDocument(docId),
    onSuccess: async () => {
      message.success("文档已删除");
      await queryClient.invalidateQueries({ queryKey: ["documents", kbId] });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const reindexMutation = useMutation({
    mutationFn: async (docId: string) => reindexDocument(docId),
    onSuccess: async (job) => {
      message.success("已发起重建索引");
      setActiveJobId(job.job_id);
      pushHistoryJob(job.job_id);
      await queryClient.invalidateQueries({ queryKey: ["documents", kbId] });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const cancelMutation = useMutation({
    mutationFn: async (jobId: string) => cancelIngestJob(jobId),
    onSuccess: async (job) => {
      message.success("任务取消请求已提交");
      setActiveJobId(job.job_id);
      pushHistoryJob(job.job_id);
      await queryClient.invalidateQueries({ queryKey: ["documents", kbId] });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const retryMutation = useMutation({
    mutationFn: async (jobId: string) => retryIngestJob(jobId),
    onSuccess: async (job) => {
      message.success("任务重试已创建");
      setActiveJobId(job.job_id);
      pushHistoryJob(job.job_id);
      await queryClient.invalidateQueries({ queryKey: ["documents", kbId] });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const firstError = useMemo(() => {
    if (deleteMutation.isError) return normalizeApiError(deleteMutation.error);
    if (reindexMutation.isError) return normalizeApiError(reindexMutation.error);
    if (cancelMutation.isError) return normalizeApiError(cancelMutation.error);
    if (retryMutation.isError) return normalizeApiError(retryMutation.error);
    if (documentsQuery.isError) return normalizeApiError(documentsQuery.error);
    if (jobQuery.isError) return normalizeApiError(jobQuery.error);
    if (kbQuery.isError) return normalizeApiError(kbQuery.error);
    return null;
  }, [
    cancelMutation.error,
    cancelMutation.isError,
    deleteMutation.error,
    deleteMutation.isError,
    documentsQuery.error,
    documentsQuery.isError,
    jobQuery.error,
    jobQuery.isError,
    kbQuery.error,
    kbQuery.isError,
    reindexMutation.error,
    reindexMutation.isError,
    retryMutation.error,
    retryMutation.isError
  ]);

  const allDocuments = useMemo(() => documentsQuery.data?.items ?? [], [documentsQuery.data?.items]);
  const indexedCount = allDocuments.filter((item) => item.status === "indexed").length;
  const processingCount = allDocuments.filter(
    (item) => item.status === "pending" || item.status === "processing"
  ).length;
  const failedCount = allDocuments.filter((item) => item.status === "failed").length;
  const filteredDocuments = useMemo(() => {
    if (docStatusFilter === "all") {
      return allDocuments;
    }
    return allDocuments.filter((item) => item.status === docStatusFilter);
  }, [allDocuments, docStatusFilter]);

  const kbNameMap = useMemo(
    () => new Map((kbQuery.data?.items ?? []).map((item) => [item.kb_id, item.name])),
    [kbQuery.data?.items]
  );
  const docNameMap = useMemo(
    () => new Map(allDocuments.map((item) => [item.doc_id, item.doc_name])),
    [allDocuments]
  );
  const activeJobStatus = jobQuery.data ? JOB_STATUS_META[jobQuery.data.status] : null;
  const documentStatusChartItems = [
    { key: "indexed", label: "已索引", value: indexedCount, color: "#16a34a" },
    { key: "processing", label: "处理中", value: processingCount, color: "#2563eb" },
    { key: "failed", label: "失败", value: failedCount, color: "#dc2626" },
    {
      key: "pending",
      label: "待处理",
      value: allDocuments.filter((item) => item.status === "pending").length,
      color: "#94a3b8"
    }
  ];
  const jobStatusChartItems = [
    {
      key: "queued",
      label: "排队中",
      value: historyJobs.filter((item) => item.status === "queued").length,
      color: "#94a3b8"
    },
    {
      key: "running",
      label: "执行中",
      value: historyJobs.filter((item) => item.status === "running").length,
      color: "#2563eb"
    },
    {
      key: "succeeded",
      label: "已完成",
      value: historyJobs.filter((item) => item.status === "succeeded").length,
      color: "#16a34a"
    },
    {
      key: "failed",
      label: "失败",
      value: historyJobs.filter((item) => item.status === "failed").length,
      color: "#dc2626"
    },
    {
      key: "canceled",
      label: "已取消",
      value: historyJobs.filter((item) => item.status === "canceled").length,
      color: "#f59e0b"
    }
  ];

  const updateKbFilter = (nextKbId?: string) => {
    const nextParams = new URLSearchParams(searchParams);
    if (nextKbId) {
      nextParams.set("kb", nextKbId);
    } else {
      nextParams.delete("kb");
    }
    setSearchParams(nextParams, { replace: true });
  };

  return (
    <div className="page-stack">
      {firstError ? <RequestErrorAlert error={firstError} /> : null}

      <CompactPageHero
        kicker="文档入库"
        title="文档与任务中心"
        description="当前页面只负责文档列表、任务跟踪、失败重试与历史回看；上传入口已拆到独立页面。"
        stats={[
          { label: "文档", value: allDocuments.length },
          { label: "已索引", value: indexedCount },
          { label: "处理中", value: processingCount },
          { label: "失败", value: failedCount }
        ]}
      />

      <Card className="card-soft" size="small" title="文档状态分布">
        <MetricBarChart items={documentStatusChartItems} emptyText="暂无文档状态数据" />
      </Card>

      <div className="dashboard-grid">
        <Card className="card-soft" size="small" title="历史任务结果">
          <DonutMetricChart
            items={jobStatusChartItems}
            centerLabel="历史任务"
            centerValue={historyJobs.length}
            emptyText="暂无历史任务数据"
          />
        </Card>
        <Card className="card-soft" size="small" title="当前任务阶段趋势">
          <MiniTrendChart
            items={jobStageSnapshots}
            stroke="#2563eb"
            emptyText="等待当前任务阶段数据"
            valueFormatter={(value) =>
              getJobStageLabel(
                Object.entries(JOB_STAGE_ORDER).find(([, order]) => order === value)?.[0]
              )
            }
          />
        </Card>
      </div>

      <Card className="card-soft" size="small" title="当前任务向量写入趋势">
        <MiniTrendChart
          items={jobVectorSnapshots}
          stroke="#0ea5a0"
          emptyText="等待当前任务进度数据"
        />
      </Card>

      <Card className="card-soft split-manage-card">
        <OpsPane
          title={
            <Space size={8}>
              <FileSearchOutlined />
              <span>文档与任务</span>
            </Space>
          }
          toolbar={
            <div className="density-toolbar density-toolbar--clean">
              <div className="density-toolbar__group">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  style={{ width: 240 }}
                  placeholder="选择知识库"
                  value={kbId}
                  loading={kbQuery.isLoading}
                  options={(kbQuery.data?.items ?? []).map((item) => ({
                    value: item.kb_id,
                    label: item.name
                  }))}
                  onChange={(value) => {
                    updateKbFilter(value);
                  }}
                />
                <Segmented<DocumentStatusFilter>
                  value={docStatusFilter}
                  options={[
                    { label: "全部", value: "all" },
                    { label: "待处理", value: "pending" },
                    { label: "处理中", value: "processing" },
                    { label: "已索引", value: "indexed" },
                    { label: "失败", value: "failed" }
                  ]}
                  onChange={(value) => {
                    setDocStatusFilter(value);
                  }}
                />
              </div>
              <div className="density-toolbar__group density-toolbar__group--meta">
                <Typography.Text className="density-meta">
                  当前 {filteredDocuments.length} / {allDocuments.length}
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
                <Button
                  type="primary"
                  icon={<ArrowRightOutlined />}
                  onClick={() => {
                    navigate(kbId ? `/admin/documents/upload?kb=${encodeURIComponent(kbId)}` : "/admin/documents/upload");
                  }}
                >
                  前往上传
                </Button>
              </div>
            </div>
          }
          extra={
            <Tooltip title="刷新文档列表">
              <Button
                shape="circle"
                icon={<ReloadOutlined />}
                onClick={() => void documentsQuery.refetch()}
                loading={documentsQuery.isFetching}
                disabled={!kbId}
                aria-label="刷新文档列表"
              />
            </Tooltip>
          }
        >
          <div className="split-pane-copy split-pane-copy--compact">
            <Typography.Text className="split-pane-copy__title">
              上传入口已拆分，当前页专注任务视角
            </Typography.Text>
            <Typography.Text className="split-pane-copy__desc">
              在这里选择知识库后统一查看文档状态、当前任务和历史任务，避免上传表单挤占管理空间。
            </Typography.Text>
          </div>

          <Card size="small" className="card-inset" title="文档列表">
            {!kbId ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请先选择知识库后查看文档列表。" />
            ) : (
              <Table
                size={tableDensity}
                className={tableDensity === "small" ? "dense-table" : undefined}
                rowKey="doc_id"
                loading={documentsQuery.isLoading}
                dataSource={filteredDocuments}
                pagination={false}
                scroll={{ y: 260 }}
                locale={{ emptyText: "当前筛选下暂无文档" }}
                columns={[
                  {
                    title: "文档",
                    dataIndex: "doc_name",
                    render: (_: string, record: DocumentItem) => (
                      <Space direction="vertical" size={2}>
                        <Typography.Text strong>{record.doc_name}</Typography.Text>
                        <Typography.Text type="secondary">
                          {record.doc_version ? `版本：${record.doc_version}` : "未填写版本"}
                          {record.published_at ? ` · 发布：${record.published_at}` : ""}
                        </Typography.Text>
                        {record.source_uri ? (
                          <Typography.Link href={record.source_uri} target="_blank" rel="noreferrer">
                            官方来源
                          </Typography.Link>
                        ) : null}
                      </Space>
                    )
                  },
                  {
                    title: "状态",
                    dataIndex: "status",
                    width: 120,
                    render: (value: DocumentItem["status"]) => {
                      const meta = DOCUMENT_STATUS_META[value];
                      return <Tag color={meta.color}>{meta.label}</Tag>;
                    }
                  },
                  {
                    title: "分块数",
                    dataIndex: "chunk_count",
                    width: 120,
                    render: (value: number) => value ?? 0
                  },
                  {
                    title: "更新时间",
                    dataIndex: "updated_at",
                    width: 140,
                    render: (value: string) => formatDateTime(value)
                  },
                  {
                    title: "操作",
                    key: "actions",
                    width: 220,
                    render: (_: unknown, record: DocumentItem) => (
                      <Space wrap>
                        <ConfirmAction
                          title="确认重建该文档索引？"
                          description="系统将重新生成文档向量索引，期间可能增加队列负载。"
                          okText="确认重建"
                          cancelText="取消"
                          onConfirm={() => {
                            reindexMutation.mutate(record.doc_id);
                          }}
                          buttonText=""
                          size="small"
                          loading={reindexMutation.isPending}
                          icon={<RetweetOutlined />}
                          shape="circle"
                          ariaLabel={`重建 ${record.doc_name} 的索引`}
                        />
                        <ConfirmAction
                          title="确认删除该文档？"
                          description="删除后将移除该文档相关向量索引，无法恢复。"
                          okText="确认删除"
                          cancelText="取消"
                          onConfirm={() => {
                            deleteMutation.mutate(record.doc_id);
                          }}
                          buttonText=""
                          danger
                          size="small"
                          loading={deleteMutation.isPending}
                          icon={<DeleteOutlined />}
                          shape="circle"
                          ariaLabel={`删除 ${record.doc_name}`}
                        />
                      </Space>
                    )
                  }
                ]}
              />
            )}
          </Card>

          <Card
            size="small"
            className="card-inset"
            style={{ marginTop: 12 }}
            title={
              <Space size={8}>
                <ClockCircleOutlined />
                <span>当前任务</span>
              </Space>
            }
            extra={
              activeJobId ? (
                <Tooltip title="刷新当前任务">
                  <Button
                    size="small"
                    shape="circle"
                    icon={<ReloadOutlined />}
                    onClick={() => void jobQuery.refetch()}
                    loading={jobQuery.isFetching}
                    aria-label="刷新当前任务"
                  />
                </Tooltip>
              ) : null
            }
          >
            {!kbId ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择知识库后查看当前任务。" />
            ) : !activeJobId ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="上传文档后会在这里显示最新任务。" />
            ) : jobQuery.isLoading ? (
              <Typography.Text type="secondary">任务状态加载中...</Typography.Text>
            ) : jobQuery.data ? (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <div className="ops-kpi-grid">
                  <div className="ops-kpi-item">
                    <span className="ops-kpi-item__label">知识库</span>
                    <span className="ops-kpi-item__value">{kbNameMap.get(jobQuery.data.kb_id) ?? "-"}</span>
                  </div>
                  <div className="ops-kpi-item">
                    <span className="ops-kpi-item__label">文档</span>
                    <span className="ops-kpi-item__value">{docNameMap.get(jobQuery.data.doc_id) ?? "处理中..."}</span>
                  </div>
                  <div className="ops-kpi-item">
                    <span className="ops-kpi-item__label">状态</span>
                    <span className="ops-kpi-item__value">
                      {activeJobStatus ? <Tag color={activeJobStatus.color}>{activeJobStatus.label}</Tag> : "-"}
                    </span>
                  </div>
                  <div className="ops-kpi-item">
                    <span className="ops-kpi-item__label">更新时间</span>
                    <span className="ops-kpi-item__value">{formatDateTime(jobQuery.data.updated_at)}</span>
                  </div>
                </div>

                <div className="ops-progress-strip">
                  <Tag color="blue">阶段：{getJobStageLabel(jobQuery.data.progress?.stage)}</Tag>
                  <Tag>页数 {jobQuery.data.progress?.pages_parsed ?? 0}</Tag>
                  <Tag>分块 {jobQuery.data.progress?.chunks_built ?? 0}</Tag>
                  <Tag>向量 {jobQuery.data.progress?.embeddings_done ?? 0}</Tag>
                  <Tag>写入 {jobQuery.data.progress?.vectors_upserted ?? 0}</Tag>
                </div>

                {jobQuery.data.error_message ? (
                  <Alert type="error" showIcon message={jobQuery.data.error_message} />
                ) : null}

                <Space wrap>
                  <Tooltip title="取消当前任务">
                    <span>
                      <ConfirmAction
                        title="确认取消当前任务？"
                        description="取消后当前入库流程会被中止，可在后续重新重试。"
                        okText="确认取消"
                        cancelText="返回"
                        onConfirm={() => {
                          if (activeJobId) {
                            cancelMutation.mutate(activeJobId);
                          }
                        }}
                        buttonText=""
                        disabled={!activeJobId || !["queued", "running"].includes(jobQuery.data.status)}
                        loading={cancelMutation.isPending}
                        icon={<StopOutlined />}
                        shape="circle"
                        ariaLabel="取消当前任务"
                      />
                    </span>
                  </Tooltip>
                  <Tooltip title="重试当前任务">
                    <span>
                      <ConfirmAction
                        title="确认重试当前任务？"
                        description="系统会创建新的入库任务并重新执行处理流程。"
                        okText="确认重试"
                        cancelText="返回"
                        onConfirm={() => {
                          if (activeJobId) {
                            retryMutation.mutate(activeJobId);
                          }
                        }}
                        buttonText=""
                        disabled={!activeJobId || !["failed", "canceled"].includes(jobQuery.data.status)}
                        loading={retryMutation.isPending}
                        icon={<SyncOutlined />}
                        shape="circle"
                        ariaLabel="重试当前任务"
                      />
                    </span>
                  </Tooltip>
                </Space>
              </Space>
            ) : (
              <Typography.Text type="secondary">暂无任务详情。</Typography.Text>
            )}
          </Card>

          <Card
            size="small"
            className="card-inset"
            title={
              <Space size={8}>
                <HistoryOutlined />
                <span>任务历史</span>
              </Space>
            }
            extra={
              <Tooltip title="刷新任务历史">
                <Button
                  size="small"
                  shape="circle"
                  icon={<ReloadOutlined />}
                  onClick={() => {
                    historyQueries.forEach((query) => {
                      void query.refetch();
                    });
                  }}
                  disabled={!historyJobs.length}
                  aria-label="刷新任务历史"
                />
              </Tooltip>
            }
            style={{ marginTop: 12 }}
          >
            {!kbId ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择知识库后查看任务历史。" />
            ) : !historyJobs.length ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史任务。" />
            ) : (
              <Table
                size={tableDensity}
                className={tableDensity === "small" ? "dense-table" : undefined}
                rowKey="job_id"
                dataSource={historyJobs}
                pagination={false}
                scroll={{ y: 250 }}
                columns={[
                  {
                    title: "文档",
                    dataIndex: "doc_id",
                    render: (value: string) => docNameMap.get(value) ?? "未知文档"
                  },
                  {
                    title: "状态",
                    dataIndex: "status",
                    width: 120,
                    render: (value: IngestJob["status"]) => {
                      const meta = JOB_STATUS_META[value];
                      return <Tag color={meta.color}>{meta.label}</Tag>;
                    }
                  },
                  {
                    title: "阶段",
                    key: "stage",
                    width: 130,
                    render: (_: unknown, record: IngestJob) => getJobStageLabel(record.progress?.stage)
                  },
                  {
                    title: "更新时间",
                    dataIndex: "updated_at",
                    width: 140,
                    render: (value: string) => formatDateTime(value)
                  },
                  {
                    title: "操作",
                    key: "actions",
                    width: 230,
                    render: (_: unknown, record: IngestJob) => (
                      <Space wrap>
                        <Tooltip title="查看">
                          <Button
                            size="small"
                            shape="circle"
                            icon={<CheckCircleOutlined />}
                            onClick={() => {
                              setActiveJobId(record.job_id);
                            }}
                            aria-label="查看任务详情"
                          />
                        </Tooltip>
                        <ConfirmAction
                          title="确认取消该任务？"
                          okText="确认取消"
                          cancelText="返回"
                          disabled={!["queued", "running"].includes(record.status)}
                          onConfirm={() => {
                            cancelMutation.mutate(record.job_id);
                          }}
                          buttonText=""
                          size="small"
                          icon={<StopOutlined />}
                          shape="circle"
                          ariaLabel="取消历史任务"
                        />
                        <ConfirmAction
                          title="确认重试该任务？"
                          okText="确认重试"
                          cancelText="返回"
                          disabled={!["failed", "canceled"].includes(record.status)}
                          onConfirm={() => {
                            retryMutation.mutate(record.job_id);
                          }}
                          buttonText=""
                          size="small"
                          icon={<SyncOutlined />}
                          shape="circle"
                          ariaLabel="重试历史任务"
                        />
                      </Space>
                    )
                  }
                ]}
              />
            )}
          </Card>
        </OpsPane>
      </Card>
    </div>
  );
}
