import { useEffect, useMemo, useState } from "react";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  InboxOutlined,
  ReloadOutlined,
  RetweetOutlined,
  StopOutlined,
  SyncOutlined
} from "@ant-design/icons";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
  message
} from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import {
  cancelIngestJob,
  deleteDocument,
  DocumentItem,
  fetchDocuments,
  fetchIngestJob,
  IngestJob,
  reindexDocument,
  retryIngestJob,
  uploadDocument
} from "../../shared/api/modules/documents";
import { fetchKbList } from "../../shared/api/modules/kb";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
import { OpsPane, OpsWorkbench } from "../../shared/components/OpsWorkbench";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";

interface UploadFormValues {
  kb_id: string;
  doc_name?: string;
  doc_version?: string;
  published_at?: string;
}

interface DocumentsPageProps {
  initialKbId?: string;
}

type TableDensity = "middle" | "small";
type DocumentStatusFilter = "all" | DocumentItem["status"];

const FINAL_JOB_STATUS = new Set(["succeeded", "failed", "canceled"]);
const JOB_HISTORY_LIMIT = 40;
const UPLOAD_ACCEPT = ".pdf,.docx,.html,.htm,.md,.txt";
const UPLOAD_FORMAT_HINT = "支持 PDF、DOCX、HTML、Markdown、TXT";

const DOCUMENT_STATUS_META: Record<DocumentItem["status"], { label: string; color: string }> = {
  pending: { label: "待处理", color: "default" },
  processing: { label: "处理中", color: "processing" },
  indexed: { label: "已索引", color: "success" },
  failed: { label: "失败", color: "error" },
  deleted: { label: "已删除", color: "default" }
};

const JOB_STATUS_META: Record<IngestJob["status"], { label: string; color: string }> = {
  queued: { label: "排队中", color: "default" },
  running: { label: "执行中", color: "processing" },
  succeeded: { label: "已完成", color: "success" },
  failed: { label: "失败", color: "error" },
  canceled: { label: "已取消", color: "warning" }
};

const JOB_STAGE_LABEL: Record<string, string> = {
  queued: "等待调度",
  parsing: "解析文档",
  chunking: "切分内容",
  embedding: "生成向量",
  upserting: "写入索引",
  finished: "已完成"
};

function getJobHistoryStorageKey(kbId: string) {
  return `csage_ingest_jobs_${kbId}`;
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

function getJobStageLabel(stage?: string | null) {
  if (!stage) {
    return "-";
  }
  return JOB_STAGE_LABEL[stage] ?? stage;
}

export function DocumentsPage({ initialKbId }: DocumentsPageProps) {
  const queryClient = useQueryClient();
  const [form] = Form.useForm<UploadFormValues>();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobHistoryIds, setJobHistoryIds] = useState<string[]>([]);
  const [tableDensity, setTableDensity] = useState<TableDensity>("small");
  const [docStatusFilter, setDocStatusFilter] = useState<DocumentStatusFilter>("all");
  const kbId = Form.useWatch("kb_id", form);

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
      return;
    }
    try {
      const raw = window.localStorage.getItem(getJobHistoryStorageKey(kbId));
      const parsed = raw ? (JSON.parse(raw) as string[]) : [];
      const ids = parsed.filter((item) => typeof item === "string");
      setJobHistoryIds(ids);
      setActiveJobId(ids[0] ?? null);
    } catch {
      setJobHistoryIds([]);
      setActiveJobId(null);
    }
  }, [kbId]);

  const saveHistory = (ids: string[]) => {
    if (!kbId) {
      return;
    }
    try {
      window.localStorage.setItem(getJobHistoryStorageKey(kbId), JSON.stringify(ids));
    } catch {
      // 本地存储失败不阻塞主流程。
    }
  };

  const pushHistoryJob = (jobId: string) => {
    setJobHistoryIds((previous) => {
      const next = [jobId, ...previous.filter((item) => item !== jobId)].slice(0, JOB_HISTORY_LIMIT);
      saveHistory(next);
      return next;
    });
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

  const uploadMutation = useMutation({
    mutationFn: async (values: UploadFormValues) => {
      const targetFile = fileList[0];
      if (!targetFile?.originFileObj) {
        throw new Error("请先选择文件");
      }
      return uploadDocument({
        kbId: values.kb_id,
        file: targetFile.originFileObj,
        docName: values.doc_name?.trim() || undefined,
        docVersion: values.doc_version?.trim() || undefined,
        publishedAt: values.published_at?.trim() || undefined
      });
    },
    onSuccess: async (data) => {
      message.success("上传成功，已触发入库任务");
      setActiveJobId(data.job.job_id);
      pushHistoryJob(data.job.job_id);
      setFileList([]);
      form.setFieldsValue({ doc_name: undefined, doc_version: undefined, published_at: undefined });
      await queryClient.invalidateQueries({ queryKey: ["documents", data.doc.kb_id] });
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

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
    if (uploadMutation.isError) return normalizeApiError(uploadMutation.error);
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
    retryMutation.isError,
    uploadMutation.error,
    uploadMutation.isError
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

  return (
    <div className="page-stack">
      {firstError ? <RequestErrorAlert error={firstError} /> : null}

      <Card className="hero-card">
        <div className="hero-layout">
          <Space direction="vertical" size={10} style={{ width: "100%" }}>
            <span className="hero-kicker">Documents Ops</span>
            <Typography.Title level={4} className="hero-title">
              文档入库工作台
            </Typography.Title>
            <Typography.Text className="hero-desc">
              把上传、任务跟踪、失败重试和历史回看放到同一视图，减少在管理端来回切换。
            </Typography.Text>
            <div className="hero-note">
              <span className="hero-note__item">上传入口保留主路径</span>
              <span className="hero-note__item">任务状态集中呈现</span>
              <span className="hero-note__item">列表操作改为图标化短动作</span>
            </div>
          </Space>
          <div className="summary-grid">
            <div className="summary-item">
              <div className="summary-item-label">当前 KB 文档数</div>
              <div className="summary-item-value">{allDocuments.length}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">已索引</div>
              <div className="summary-item-value">{indexedCount}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">处理中</div>
              <div className="summary-item-value">{processingCount}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">失败文档</div>
              <div className="summary-item-value">{failedCount}</div>
            </div>
          </div>
        </div>
      </Card>

      <OpsWorkbench
        left={
          <OpsPane
            title={
              <Space size={8}>
                <CloudUploadOutlined />
                <span>文档投递</span>
              </Space>
            }
            introTitle="上传后立即进入任务监控"
            introDescription="支持 PDF、DOCX、HTML、Markdown、TXT。建议按知识库分批上传，方便观察解析、切分、向量写入的处理阶段。"
          >
              <Form<UploadFormValues>
                form={form}
                layout="vertical"
                initialValues={{ published_at: undefined, kb_id: initialKbId }}
                onFinish={(values) => {
                  uploadMutation.mutate(values);
                }}
              >
                <Form.Item
                  name="kb_id"
                  label="知识库"
                  rules={[{ required: true, message: "请选择知识库" }]}
                >
                  <Select
                    loading={kbQuery.isLoading}
                    placeholder="选择要投递的知识库"
                    options={(kbQuery.data?.items ?? []).map((item) => ({
                      label: item.name,
                      value: item.kb_id
                    }))}
                  />
                </Form.Item>
                <Form.Item label="文档文件" required>
                  <Upload
                    maxCount={1}
                    beforeUpload={() => false}
                    fileList={fileList}
                    onChange={({ fileList: nextList }) => {
                      setFileList(nextList);
                    }}
                    accept={UPLOAD_ACCEPT}
                  >
                    <Button icon={<InboxOutlined />}>选择文件</Button>
                  </Upload>
                  <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                    {UPLOAD_FORMAT_HINT}
                  </Typography.Paragraph>
                </Form.Item>
                <Form.Item name="doc_name" label="文档名称（可选）">
                  <Input placeholder="默认使用文件名" />
                </Form.Item>
                <Form.Item name="doc_version" label="文档版本（可选）">
                  <Input placeholder="例如：2026 春季版" />
                </Form.Item>
                <Form.Item name="published_at" label="发布日期（可选）">
                  <Input placeholder="YYYY-MM-DD" />
                </Form.Item>
                <Form.Item style={{ marginBottom: 0 }}>
                  <Button
                    type="primary"
                    htmlType="submit"
                    icon={<CloudUploadOutlined />}
                    loading={uploadMutation.isPending}
                    block
                  >
                    上传并入库
                  </Button>
                </Form.Item>
              </Form>

              <Card
                size="small"
                className="card-inset"
                style={{ marginTop: 16 }}
                title={
                  <Space size={8}>
                    <ClockCircleOutlined />
                    <span>当前任务</span>
                  </Space>
                }
                extra={
                  activeJobId ? (
                    <Button
                      size="small"
                      icon={<ReloadOutlined />}
                      onClick={() => void jobQuery.refetch()}
                      loading={jobQuery.isFetching}
                      aria-label="刷新当前任务"
                    >
                      刷新
                    </Button>
                  ) : null
                }
              >
                {!activeJobId ? (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="上传文档后会在这里显示最新任务。" />
                ) : jobQuery.isLoading ? (
                  <Typography.Text type="secondary">任务状态加载中...</Typography.Text>
                ) : jobQuery.data ? (
                  <Space direction="vertical" size={12} style={{ width: "100%" }}>
                    <div className="ops-kpi-grid">
                      <div className="ops-kpi-item">
                        <span className="ops-kpi-item__label">知识库</span>
                        <span className="ops-kpi-item__value">
                          {kbNameMap.get(jobQuery.data.kb_id) ?? "-"}
                        </span>
                      </div>
                      <div className="ops-kpi-item">
                        <span className="ops-kpi-item__label">文档</span>
                        <span className="ops-kpi-item__value">
                          {docNameMap.get(jobQuery.data.doc_id) ?? "处理中..."}
                        </span>
                      </div>
                      <div className="ops-kpi-item">
                        <span className="ops-kpi-item__label">状态</span>
                        <span className="ops-kpi-item__value">
                          {activeJobStatus ? (
                            <Tag color={activeJobStatus.color}>{activeJobStatus.label}</Tag>
                          ) : (
                            "-"
                          )}
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
                        buttonText="取消"
                        disabled={!activeJobId || !["queued", "running"].includes(jobQuery.data.status)}
                        loading={cancelMutation.isPending}
                        icon={<StopOutlined />}
                        ariaLabel="取消当前任务"
                      />
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
                        buttonText="重试"
                        disabled={!activeJobId || !["failed", "canceled"].includes(jobQuery.data.status)}
                        loading={retryMutation.isPending}
                        icon={<SyncOutlined />}
                        ariaLabel="重试当前任务"
                      />
                    </Space>
                  </Space>
                ) : (
                    <Typography.Text type="secondary">暂无任务详情。</Typography.Text>
                )}
              </Card>
          </OpsPane>
        }
        right={
          <OpsPane
            title={
              <Space size={8}>
                <FileSearchOutlined />
                <span>文档与任务</span>
              </Space>
            }
            toolbar={
              <div className="density-toolbar">
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
              <Space>
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
                </Space>
              </div>
            }
          >
              <Card
                size="small"
                className="card-inset"
                title="文档列表"
                extra={
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={() => void documentsQuery.refetch()}
                    loading={documentsQuery.isFetching}
                    aria-label="刷新文档列表"
                  >
                    刷新
                  </Button>
                }
              >
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
                              buttonText="重建"
                              size="small"
                              loading={reindexMutation.isPending}
                              icon={<RetweetOutlined />}
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
                              buttonText="删除"
                              danger
                              size="small"
                              loading={deleteMutation.isPending}
                              icon={<DeleteOutlined />}
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
                title={
                  <Space size={8}>
                    <HistoryOutlined />
                    <span>任务历史</span>
                  </Space>
                }
                extra={
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={() => {
                      historyQueries.forEach((query) => {
                        void query.refetch();
                      });
                    }}
                    disabled={!historyJobs.length}
                    aria-label="刷新任务历史"
                  >
                    刷新
                  </Button>
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
                            <Button
                              size="small"
                              icon={<CheckCircleOutlined />}
                              onClick={() => {
                                setActiveJobId(record.job_id);
                              }}
                            >
                              查看
                            </Button>
                            <ConfirmAction
                              title="确认取消该任务？"
                              okText="确认取消"
                              cancelText="返回"
                              disabled={!['queued', 'running'].includes(record.status)}
                              onConfirm={() => {
                                cancelMutation.mutate(record.job_id);
                              }}
                              buttonText="取消"
                              size="small"
                              icon={<StopOutlined />}
                              ariaLabel="取消历史任务"
                            />
                            <ConfirmAction
                              title="确认重试该任务？"
                              okText="确认重试"
                              cancelText="返回"
                              disabled={!['failed', 'canceled'].includes(record.status)}
                              onConfirm={() => {
                                retryMutation.mutate(record.job_id);
                              }}
                              buttonText="重试"
                              size="small"
                              icon={<SyncOutlined />}
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
        }
      />
    </div>
  );
}
