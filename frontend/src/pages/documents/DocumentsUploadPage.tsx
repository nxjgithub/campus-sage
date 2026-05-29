import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  EyeOutlined,
  FileTextOutlined,
  InboxOutlined,
  PictureOutlined
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Form,
  Image,
  Input,
  Modal,
  Segmented,
  Select,
  Space,
  Steps,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { UploadFile } from "antd/es/upload/interface";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiClient } from "../../shared/api/client";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import {
  buildStagedPreview,
  commitStagedDocument,
  StagedAsset,
  StagedChunk,
  StagedDocument,
  StagedPreviewBlock,
  updateStagedChunk,
  uploadStagedDocument
} from "../../shared/api/modules/documents";
import { fetchKbList } from "../../shared/api/modules/kb";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import { pushJobHistoryId, UPLOAD_ACCEPT, UPLOAD_FORMAT_HINT, UploadFormValues } from "./documentsShared";
import type { UploadInputMode } from "./documentsShared";

const DEFAULT_TEXT_DOC_NAME = "粘贴文本";

export function DocumentsUploadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm<UploadFormValues>();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [preview, setPreview] = useState<StagedDocument | null>(null);
  const [activeStep, setActiveStep] = useState(0);
  const [editingChunk, setEditingChunk] = useState<StagedChunk | null>(null);
  const [editingText, setEditingText] = useState("");
  const [inputMode, setInputMode] = useState<UploadInputMode>("file");

  const initialKbId = searchParams.get("kb") ?? undefined;

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList
  });

  const kbNameMap = useMemo(
    () => new Map((kbQuery.data?.items ?? []).map((item) => [item.kb_id, item.name] as const)),
    [kbQuery.data?.items]
  );

  const uploadPreviewMutation = useMutation({
    mutationFn: async (values: UploadFormValues) => {
      const targetFile = resolveUploadFile(inputMode, values, fileList[0]?.originFileObj);
      const docName =
        values.doc_name?.trim() ||
        (inputMode === "text" ? DEFAULT_TEXT_DOC_NAME : undefined);
      const staged = await uploadStagedDocument({
        kbId: values.kb_id,
        file: targetFile,
        docName,
        docVersion: values.doc_version?.trim() || undefined,
        publishedAt: values.published_at?.trim() || undefined,
        sourceUri: values.source_uri?.trim() || undefined
      });
      return buildStagedPreview(staged.staged_doc_id);
    },
    onSuccess: (data) => {
      setPreview(data);
      setActiveStep(1);
      message.success("解析预览已生成");
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const chunkMutation = useMutation({
    mutationFn: updateStagedChunk,
    onSuccess: (data) => {
      setPreview(data);
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const commitMutation = useMutation({
    mutationFn: async () => {
      if (!preview) {
        throw new Error("请先生成预览");
      }
      return commitStagedDocument(preview.staged_doc_id);
    },
    onSuccess: async (data) => {
      message.success("已确认入库，后台任务开始执行");
      pushJobHistoryId(data.doc.kb_id, data.job.job_id);
      await queryClient.invalidateQueries({ queryKey: ["documents", data.doc.kb_id] });
      navigate(`/admin/documents?kb=${encodeURIComponent(data.doc.kb_id)}`);
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const firstError = useMemo(() => {
    if (uploadPreviewMutation.isError) return normalizeApiError(uploadPreviewMutation.error);
    if (chunkMutation.isError) return normalizeApiError(chunkMutation.error);
    if (commitMutation.isError) return normalizeApiError(commitMutation.error);
    if (kbQuery.isError) return normalizeApiError(kbQuery.error);
    return null;
  }, [
    chunkMutation.error,
    chunkMutation.isError,
    commitMutation.error,
    commitMutation.isError,
    kbQuery.error,
    kbQuery.isError,
    uploadPreviewMutation.error,
    uploadPreviewMutation.isError
  ]);

  const watchedKbId = Form.useWatch("kb_id", form) ?? initialKbId ?? "";
  const rawText = Form.useWatch("raw_text", form) ?? "";
  const selectedKbName = kbNameMap.get(watchedKbId) ?? "未选择";
  const selectedFileName = fileList[0]?.name ?? "未选择";
  const selectedSourceName =
    inputMode === "text"
      ? rawText.trim()
        ? `粘贴文本（${rawText.trim().length} 字）`
        : "未输入"
      : selectedFileName;
  const enabledChunkCount = preview?.chunks.filter((item) => item.enabled).length ?? 0;
  const disabledChunkCount = (preview?.chunks.length ?? 0) - enabledChunkCount;
  const imageChunkCount = preview?.chunks.filter((item) => item.source_kind === "image_asset").length ?? 0;

  const chunkColumns: ColumnsType<StagedChunk> = [
    {
      title: "入库",
      dataIndex: "enabled",
      width: 72,
      render: (_, record) => (
        <Switch
          size="small"
          checked={record.enabled}
          loading={chunkMutation.isPending && chunkMutation.variables?.chunkId === record.chunk_id}
          onChange={(checked) => {
            if (!preview) return;
            chunkMutation.mutate({
              stagedDocId: preview.staged_doc_id,
              chunkId: record.chunk_id,
              enabled: checked
            });
          }}
        />
      )
    },
    {
      title: "类型",
      dataIndex: "source_kind",
      width: 100,
      render: (value: string) =>
        value === "image_asset" ? <Tag color="blue">图片</Tag> : <Tag>正文</Tag>
    },
    {
      title: "位置",
      width: 180,
      render: (_, record) => record.asset_label || record.section_path || record.page_start || "-"
    },
    {
      title: "内容预览",
      dataIndex: "text",
      render: (value: string, record) => (
        <button
          className="link-button"
          type="button"
          onClick={() => {
            setEditingChunk(record);
            setEditingText(value);
          }}
        >
          {value.length > 120 ? `${value.slice(0, 120)}...` : value}
        </button>
      )
    }
  ];

  return (
    <div className="page-stack">
      {firstError ? <RequestErrorAlert error={firstError} /> : null}

      <Card className="card-soft split-overview-card">
        <div className="split-overview">
          <div className="split-overview__copy">
            <div className="split-overview__label-row">
              <span className="hero-kicker">文档入库</span>
              <Typography.Text className="split-overview__eyebrow">
                先预览解析结果，再确认写入向量库。
              </Typography.Text>
            </div>
            <Typography.Title level={3} className="hero-title">
              上传、预览、确认入库
            </Typography.Title>
            <Typography.Paragraph className="split-overview__desc">
              页面会展示正文、图片资产和分块结果。图片不会直接写入向量库，系统会保存原图并用图片资产分块建立可引用入口。
            </Typography.Paragraph>
          </div>
          <div className="split-overview__stats">
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">目标知识库</span>
              <span className="split-overview-stat__value">{selectedKbName}</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">来源</span>
              <span className="split-overview-stat__value">{selectedSourceName}</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">图片资产</span>
              <span className="split-overview-stat__value">{preview?.assets.length ?? 0}</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">确认分块</span>
              <span className="split-overview-stat__value">{enabledChunkCount}</span>
            </div>
          </div>
        </div>
      </Card>

      <Card
        className="card-soft"
        title={
          <Space size={8}>
            <CloudUploadOutlined />
            <span>入库工作台</span>
          </Space>
        }
        extra={
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => {
              navigate(
                initialKbId
                  ? `/admin/documents?kb=${encodeURIComponent(initialKbId)}`
                  : "/admin/documents"
              );
            }}
          >
            返回管理页
          </Button>
        }
      >
        <Steps
          current={activeStep}
          items={[
            { title: "上传", icon: <CloudUploadOutlined /> },
            { title: "预览", icon: <EyeOutlined /> },
            { title: "确认", icon: <CheckCircleOutlined /> }
          ]}
        />

        <div className="split-create-layout" style={{ marginTop: 24 }}>
          <div className="split-create-main">
            <Form<UploadFormValues>
              form={form}
              layout="vertical"
              initialValues={{ published_at: undefined, kb_id: initialKbId, input_mode: "file" }}
              onFinish={(values) => {
                uploadPreviewMutation.mutate(values);
              }}
            >
              <Form.Item name="kb_id" label="知识库" rules={[{ required: true, message: "请选择知识库" }]}>
                <Select
                  loading={kbQuery.isLoading}
                  placeholder="选择要投递的知识库"
                  options={(kbQuery.data?.items ?? []).map((item) => ({
                    label: item.name,
                    value: item.kb_id
                  }))}
                  disabled={Boolean(preview)}
                />
              </Form.Item>
              <Form.Item label="入库方式">
                <Segmented
                  value={inputMode}
                  disabled={Boolean(preview)}
                  options={[
                    { label: "上传文件", value: "file" },
                    { label: "粘贴文本", value: "text" }
                  ]}
                  onChange={(value) => {
                    const nextMode = value as UploadInputMode;
                    setInputMode(nextMode);
                    form.setFieldValue("input_mode", nextMode);
                    if (nextMode === "text") {
                      setFileList([]);
                    }
                  }}
                />
              </Form.Item>
              {inputMode === "text" ? (
                <Form.Item
                  name="raw_text"
                  label="文本内容"
                  required
                  rules={[
                    {
                      validator: (_, value) => {
                        if (typeof value === "string" && value.trim()) {
                          return Promise.resolve();
                        }
                        return Promise.reject(new Error("请粘贴要入库的文本内容"));
                      }
                    }
                  ]}
                >
                  <Input.TextArea
                    disabled={Boolean(preview)}
                    rows={10}
                    showCount
                    placeholder="粘贴一段公告、制度、问答材料或网页正文，系统会按 TXT 文档生成预览和分块。"
                  />
                </Form.Item>
              ) : (
                <Form.Item label="文档文件" required>
                  <Upload
                    maxCount={1}
                    beforeUpload={() => false}
                    fileList={fileList}
                    disabled={Boolean(preview)}
                    onChange={({ fileList: nextList }) => {
                      setFileList(nextList);
                    }}
                    accept={UPLOAD_ACCEPT}
                  >
                    <Tooltip title="选择文件">
                      <Button shape="circle" icon={<InboxOutlined />} aria-label="选择文件" />
                    </Tooltip>
                  </Upload>
                  <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                    {UPLOAD_FORMAT_HINT}
                  </Typography.Paragraph>
                </Form.Item>
              )}
              <Form.Item name="doc_name" label="文档名称（可选）">
                <Input
                  disabled={Boolean(preview)}
                  placeholder={inputMode === "text" ? "默认使用“粘贴文本”" : "默认使用文件名"}
                />
              </Form.Item>
              <Form.Item name="doc_version" label="文档版本（可选）">
                <Input disabled={Boolean(preview)} placeholder="例如：2026 春季版" />
              </Form.Item>
              <Form.Item name="published_at" label="发布日期（可选）">
                <Input disabled={Boolean(preview)} placeholder="YYYY-MM-DD" />
              </Form.Item>
              <Form.Item name="source_uri" label="官方来源链接（可选）">
                <Input disabled={Boolean(preview)} placeholder="https://example.edu/policy" />
              </Form.Item>

              <div className="split-actions">
                <Button
                  onClick={() => {
                    setPreview(null);
                    setActiveStep(0);
                    setFileList([]);
                    setInputMode("file");
                    form.resetFields();
                  }}
                >
                  重置
                </Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<EyeOutlined />}
                  loading={uploadPreviewMutation.isPending}
                  disabled={Boolean(preview)}
                >
                  上传并生成预览
                </Button>
              </div>
            </Form>
          </div>

          <aside className="split-create-aside">
            <section className="split-side-card">
              <Typography.Text className="split-side-card__title">预览摘要</Typography.Text>
              <div className="split-side-metrics">
                <div className="split-side-metric">
                  <span className="split-side-metric__label">页面</span>
                  <span className="split-side-metric__value">{preview?.pages.length ?? 0}</span>
                </div>
                <div className="split-side-metric">
                  <span className="split-side-metric__label">分块</span>
                  <span className="split-side-metric__value">{preview?.chunks.length ?? 0}</span>
                </div>
                <div className="split-side-metric">
                  <span className="split-side-metric__label">图片分块</span>
                  <span className="split-side-metric__value">{imageChunkCount}</span>
                </div>
                <div className="split-side-metric">
                  <span className="split-side-metric__label">已剔除</span>
                  <span className="split-side-metric__value">{disabledChunkCount}</span>
                </div>
              </div>
            </section>
          </aside>
        </div>
      </Card>

      {preview ? (
        <Card className="card-soft" title="解析预览">
          {preview.warnings.length ? (
            <Alert
              showIcon
              type="warning"
              message="质量提醒"
              description={preview.warnings.join("；")}
              style={{ marginBottom: 16 }}
            />
          ) : null}
          <Tabs
            items={[
              {
                key: "pages",
                label: (
                  <Space>
                    <FileTextOutlined />
                    正文
                  </Space>
                ),
                children: <DocumentPreview preview={preview} />
              },
              {
                key: "assets",
                label: (
                  <Space>
                    <PictureOutlined />
                    图片
                  </Space>
                ),
                children: <AssetPreview assets={preview.assets} />
              },
              {
                key: "chunks",
                label: "分块",
                children: (
                  <Table
                    rowKey="chunk_id"
                    size="small"
                    columns={chunkColumns}
                    dataSource={preview.chunks}
                    pagination={{ pageSize: 8 }}
                  />
                )
              }
            ]}
          />
          <div className="split-actions" style={{ marginTop: 16 }}>
            <Button
              onClick={() => {
                setActiveStep(1);
              }}
            >
              继续检查
            </Button>
            <Button
              type="primary"
              icon={<CheckCircleOutlined />}
              loading={commitMutation.isPending}
              disabled={enabledChunkCount === 0}
              onClick={() => {
                setActiveStep(2);
                commitMutation.mutate();
              }}
            >
              确认入库
            </Button>
          </div>
        </Card>
      ) : null}

      <Modal
        title="编辑分块"
        open={Boolean(editingChunk)}
        onCancel={() => {
          setEditingChunk(null);
          setEditingText("");
        }}
        onOk={() => {
          if (!preview || !editingChunk) return;
          chunkMutation.mutate({
            stagedDocId: preview.staged_doc_id,
            chunkId: editingChunk.chunk_id,
            text: editingText
          });
          setEditingChunk(null);
          setEditingText("");
        }}
      >
        <Input.TextArea
          rows={8}
          value={editingText}
          onChange={(event) => {
            setEditingText(event.target.value);
          }}
        />
      </Modal>
    </div>
  );
}

function resolveUploadFile(
  inputMode: UploadInputMode,
  values: UploadFormValues,
  selectedFile?: File
) {
  if (inputMode === "text") {
    const text = values.raw_text?.trim() ?? "";
    if (!text) {
      throw new Error("请先粘贴文本内容");
    }
    return new File([text], buildTextFileName(values.doc_name), {
      type: "text/plain;charset=utf-8"
    });
  }
  if (!selectedFile) {
    throw new Error("请先选择文件");
  }
  return selectedFile;
}

function buildTextFileName(docName?: string) {
  const rawName = docName?.trim() || DEFAULT_TEXT_DOC_NAME;
  const safeName = rawName.replace(/[\\/:*?"<>|]/g, "_").trim() || DEFAULT_TEXT_DOC_NAME;
  return safeName.toLowerCase().endsWith(".txt") ? safeName : `${safeName}.txt`;
}

function DocumentPreview({ preview }: { preview: StagedDocument }) {
  const blocks = preview.preview_blocks ?? [];
  if (!blocks.length && !preview.pages.length) {
    return <Alert type="info" showIcon message="未解析出正文页面" />;
  }
  if (blocks.length) {
    return (
      <div className="document-preview-shell">
        <div className="document-preview-page">
          {blocks.slice(0, 120).map((block) => (
            <PreviewBlock block={block} key={`${block.order_index}_${block.block_type}`} />
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="page-stack">
      {preview.pages.slice(0, 8).map((page, index) => (
        <section className="split-side-card" key={`${page.page_number ?? "p"}-${index}`}>
          <Typography.Text className="split-side-card__title">
            {page.section_path || (page.page_number ? `第 ${page.page_number} 页` : `片段 ${index + 1}`)}
          </Typography.Text>
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
            {page.text}
          </Typography.Paragraph>
        </section>
      ))}
    </div>
  );
}

function PreviewBlock({ block }: { block: StagedPreviewBlock }) {
  if (block.block_type === "heading") {
    const level = Math.min(Math.max(block.level ?? 2, 1), 6);
    const className = `document-preview-heading document-preview-heading--${level}`;
    return <div className={className}>{block.text}</div>;
  }
  if (block.block_type === "table" && block.rows?.length) {
    return (
      <div className="document-preview-table-wrap">
        <table className="document-preview-table">
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={`${block.order_index}_${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`${block.order_index}_${rowIndex}_${cellIndex}`}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (block.block_type === "image" && block.asset_url) {
    return (
      <figure className="document-preview-image">
        <AuthorizedImage asset={{ url: block.asset_url, label: block.asset_label ?? "图片" }} />
        <figcaption>{block.asset_label ?? block.text ?? "图片"}</figcaption>
      </figure>
    );
  }
  return <p className="document-preview-paragraph">{block.text}</p>;
}

function AssetPreview({ assets }: { assets: StagedAsset[] }) {
  if (!assets.length) {
    return <Alert type="info" showIcon message="未发现图片资产" />;
  }
  return (
    <div className="asset-preview-grid">
      {assets.map((asset) => (
        <section className="split-side-card" key={asset.asset_id}>
          <Typography.Text className="split-side-card__title">
            {asset.label} · {asset.file_name}
          </Typography.Text>
          <AuthorizedImage asset={asset} />
        </section>
      ))}
    </div>
  );
}

function AuthorizedImage({ asset }: { asset: Pick<StagedAsset, "url" | "label"> }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;
    apiClient
      .get<Blob>(asset.url.replace("/api/v1", ""), { responseType: "blob" })
      .then((response) => {
        if (revoked) return;
        objectUrl = URL.createObjectURL(response.data);
        setUrl(objectUrl);
      })
      .catch(() => {
        setUrl(null);
      });
    return () => {
      revoked = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [asset.url]);

  if (!url) {
    return <Alert type="info" showIcon message="图片加载中" />;
  }
  return <Image src={url} alt={asset.label} style={{ maxHeight: 220, objectFit: "contain" }} />;
}
