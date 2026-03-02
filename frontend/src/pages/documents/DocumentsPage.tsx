import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  Row,
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
  fetchDocuments,
  fetchIngestJob,
  reindexDocument,
  retryIngestJob,
  uploadDocument
} from "../../shared/api/modules/documents";
import { fetchKbList } from "../../shared/api/modules/kb";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
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
type DocumentStatusFilter = "all" | "indexed" | "processing" | "failed";

const FINAL_JOB_STATUS = new Set(["succeeded", "failed", "canceled"]);
const JOB_HISTORY_LIMIT = 40;

function getJobHistoryStorageKey(kbId: string) {
  return `csage_ingest_jobs_${kbId}`;
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
      // 本地存储失败不阻塞主流程
    }
  };

  const pushHistoryJob = (jobId: string) => {
    setJobHistoryIds((prev) => {
      const next = [jobId, ...prev.filter((id) => id !== jobId)].slice(0, JOB_HISTORY_LIMIT);
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
      if (!targetFile || !targetFile.originFileObj) {
        throw new Error("请先选择文件");
      }
      return uploadDocument({
        kbId: values.kb_id,
        file: targetFile.originFileObj,
        docName: values.doc_name,
        docVersion: values.doc_version,
        publishedAt: values.published_at
      });
    },
    onSuccess: async (data) => {
      message.success("上传成功，已触发入库任务");
      setActiveJobId(data.job.job_id);
      pushHistoryJob(data.job.job_id);
      setFileList([]);
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

  const hasError = useMemo(
    () =>
      kbQuery.isError ||
      documentsQuery.isError ||
      jobQuery.isError ||
      uploadMutation.isError ||
      deleteMutation.isError ||
      reindexMutation.isError ||
      cancelMutation.isError ||
      retryMutation.isError,
    [
      cancelMutation.isError,
      deleteMutation.isError,
      documentsQuery.isError,
      jobQuery.isError,
      kbQuery.isError,
      reindexMutation.isError,
      retryMutation.isError,
      uploadMutation.isError
    ]
  );

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

  const indexedCount =
    documentsQuery.data?.items.filter((item) => item.status === "indexed").length ?? 0;
  const failedCount =
    documentsQuery.data?.items.filter((item) => item.status === "failed").length ?? 0;
  const filteredDocuments = useMemo(() => {
    const items = documentsQuery.data?.items ?? [];
    if (docStatusFilter === "all") {
      return items;
    }
    return items.filter((item) => item.status === docStatusFilter);
  }, [docStatusFilter, documentsQuery.data?.items]);
  const kbNameMap = useMemo(() => {
    return new Map((kbQuery.data?.items ?? []).map((item) => [item.kb_id, item.name]));
  }, [kbQuery.data?.items]);
  const docNameMap = useMemo(() => {
    return new Map((documentsQuery.data?.items ?? []).map((item) => [item.doc_id, item.doc_name]));
  }, [documentsQuery.data?.items]);

  return (
    <div className="page-stack">
      {hasError && firstError ? <RequestErrorAlert error={firstError} /> : null}

      <Card className="hero-card">
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Typography.Title level={4} className="hero-title">
            文档入库工作台
          </Typography.Title>
          <Typography.Text className="hero-desc">
            支持上传、重建、任务监控、失败重试与历史回放，适合知识库运营日常使用。
          </Typography.Text>
          <div className="summary-grid">
            <div className="summary-item">
              <div className="summary-item-label">当前 KB 文档数</div>
              <div className="summary-item-value">{documentsQuery.data?.items.length ?? 0}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">已索引</div>
              <div className="summary-item-value">{indexedCount}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">失败</div>
              <div className="summary-item-value">{failedCount}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">历史任务</div>
              <div className="summary-item-value">{historyJobs.length}</div>
            </div>
          </div>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <Card title="上传文档并触发入库" className="card-soft">
            <Alert
              type="info"
              showIcon
              message="仅支持 PDF；建议按知识库分批上传，便于观察队列状态。"
              style={{ marginBottom: 12 }}
            />
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
                  accept=".pdf"
                >
                  <Button>选择 PDF 文件</Button>
                </Upload>
              </Form.Item>
              <Row gutter={12}>
                <Col span={24}>
                  <Form.Item name="doc_name" label="文档名称（可选）">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="doc_version" label="文档版本（可选）">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="published_at" label="发布日期（可选）">
                    <Input placeholder="YYYY-MM-DD" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={uploadMutation.isPending} block>
                  上传并入库
                </Button>
              </Form.Item>
            </Form>
          </Card>

          <Card
            title="入库任务状态"
            className="card-soft"
            style={{ marginTop: 16 }}
            extra={
              activeJobId ? <Typography.Text type="secondary">任务跟踪中</Typography.Text> : null
            }
          >
            {!activeJobId ? (
              <Typography.Text type="secondary">暂无进行中的任务。</Typography.Text>
            ) : (
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                <Typography.Text>
                  知识库：{kbNameMap.get(jobQuery.data?.kb_id ?? "") ?? "-"}
                </Typography.Text>
                <Typography.Text>
                  文档：{docNameMap.get(jobQuery.data?.doc_id ?? "") ?? "处理中..."}
                </Typography.Text>
                <Typography.Text>
                  状态：<Tag>{jobQuery.data?.status ?? "-"}</Tag>
                </Typography.Text>
                <Typography.Text>stage: {jobQuery.data?.progress?.stage ?? "-"}</Typography.Text>
                <Typography.Text>
                  pages/chunks/embeddings/upsert：
                  {jobQuery.data?.progress?.pages_parsed ?? 0}/
                  {jobQuery.data?.progress?.chunks_built ?? 0}/
                  {jobQuery.data?.progress?.embeddings_done ?? 0}/
                  {jobQuery.data?.progress?.vectors_upserted ?? 0}
                </Typography.Text>
                {jobQuery.data?.error_message ? (
                  <Typography.Text type="danger">{jobQuery.data.error_message}</Typography.Text>
                ) : null}
                <Space>
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
                    buttonText="取消任务"
                    disabled={!activeJobId}
                    loading={cancelMutation.isPending}
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
                    buttonText="重试任务"
                    disabled={!activeJobId}
                    loading={retryMutation.isPending}
                  />
                </Space>
              </Space>
            )}
          </Card>
        </Col>

        <Col xs={24} xl={14}>
          <Card
            title="文档列表"
            className={`card-soft ${tableDensity === "small" ? "ops-pane-card--dense" : ""}`}
            extra={
              <Button
                onClick={() => void documentsQuery.refetch()}
                loading={documentsQuery.isFetching}
              >
                刷新
              </Button>
            }
          >
            {!kbId ? (
              <Typography.Text type="secondary">请先选择知识库后查看文档列表。</Typography.Text>
            ) : (
              <>
                <div className="density-toolbar">
                  <Segmented<DocumentStatusFilter>
                    value={docStatusFilter}
                    options={[
                      { label: "全部", value: "all" },
                      { label: "已索引", value: "indexed" },
                      { label: "处理中", value: "processing" },
                      { label: "失败", value: "failed" }
                    ]}
                    onChange={(value) => {
                      setDocStatusFilter(value);
                    }}
                  />
                  <Space>
                    <Typography.Text className="density-meta">
                      当前 {filteredDocuments.length} / {documentsQuery.data?.items.length ?? 0}
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
                <Table
                  size={tableDensity}
                  className={tableDensity === "small" ? "dense-table" : undefined}
                  rowKey="doc_id"
                  loading={documentsQuery.isLoading}
                  dataSource={filteredDocuments}
                  pagination={false}
                  scroll={{ y: 280 }}
                  columns={[
                    { title: "文档名", dataIndex: "doc_name" },
                    {
                      title: "版本",
                      dataIndex: "doc_version",
                      width: 140,
                      render: (value: string | null | undefined) => value || "-"
                    },
                    {
                      title: "状态",
                      dataIndex: "status",
                      width: 120,
                      render: (value: string) => <Tag>{value}</Tag>
                    },
                    { title: "chunk_count", dataIndex: "chunk_count", width: 120 },
                    {
                      title: "操作",
                      key: "actions",
                      width: 240,
                      render: (_, record: { doc_id: string }) => (
                        <Space>
                          <ConfirmAction
                            title="确认重建该文档索引？"
                            description="系统将重新生成文档向量索引，期间可能增加队列负载。"
                            okText="确认重建"
                            cancelText="取消"
                            onConfirm={() => {
                              reindexMutation.mutate(record.doc_id);
                            }}
                            buttonText="重建索引"
                            size="small"
                            loading={reindexMutation.isPending}
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
                          />
                        </Space>
                      )
                    }
                  ]}
                />
              </>
            )}
          </Card>

          <Card
            title="任务历史"
            className={`card-soft ${tableDensity === "small" ? "ops-pane-card--dense" : ""}`}
            style={{ marginTop: 16 }}
            extra={
              <Button
                onClick={() => {
                  historyQueries.forEach((query) => {
                    void query.refetch();
                  });
                }}
                disabled={!historyJobs.length}
              >
                刷新历史
              </Button>
            }
          >
            {!kbId ? (
              <Typography.Text type="secondary">请选择知识库后查看任务历史。</Typography.Text>
            ) : !historyJobs.length ? (
              <Typography.Text type="secondary">暂无历史任务。</Typography.Text>
            ) : (
              <Table
                size={tableDensity}
                className={tableDensity === "small" ? "dense-table" : undefined}
                rowKey="job_id"
                dataSource={historyJobs}
                pagination={false}
                scroll={{ y: 280 }}
                columns={[
                  {
                    title: "文档名",
                    dataIndex: "doc_id",
                    width: 240,
                    render: (value: string) => docNameMap.get(value) ?? "未知文档"
                  },
                  {
                    title: "状态",
                    dataIndex: "status",
                    width: 120,
                    render: (value: string) => <Tag>{value}</Tag>
                  },
                  { title: "错误码", dataIndex: "error_code", width: 160 },
                  { title: "更新时间", dataIndex: "updated_at", width: 220 },
                  {
                    title: "操作",
                    key: "actions",
                    width: 280,
                    render: (_, record) => (
                      <Space>
                        <Button
                          size="small"
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
                          disabled={!["queued", "running"].includes(record.status)}
                          onConfirm={() => {
                            cancelMutation.mutate(record.job_id);
                          }}
                          buttonText="取消"
                          size="small"
                        />
                        <ConfirmAction
                          title="确认重试该任务？"
                          okText="确认重试"
                          cancelText="返回"
                          disabled={!["failed", "canceled"].includes(record.status)}
                          onConfirm={() => {
                            retryMutation.mutate(record.job_id);
                          }}
                          buttonText="重试"
                          size="small"
                        />
                      </Space>
                    )
                  }
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

