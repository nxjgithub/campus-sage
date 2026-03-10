import { ArrowLeftOutlined, CloudUploadOutlined, InboxOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, Select, Space, Tooltip, Typography, Upload, message } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { uploadDocument } from "../../shared/api/modules/documents";
import { fetchKbList } from "../../shared/api/modules/kb";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import { pushJobHistoryId, UPLOAD_ACCEPT, UPLOAD_FORMAT_HINT, UploadFormValues } from "./documentsShared";

export function DocumentsUploadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm<UploadFormValues>();
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const initialKbId = searchParams.get("kb") ?? undefined;

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList
  });

  const kbNameMap = useMemo(
    () =>
      new Map((kbQuery.data?.items ?? []).map((item) => [item.kb_id, item.name] as const)),
    [kbQuery.data?.items]
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
      pushJobHistoryId(data.doc.kb_id, data.job.job_id);
      setFileList([]);
      form.resetFields();
      await queryClient.invalidateQueries({ queryKey: ["documents", data.doc.kb_id] });
      navigate(`/admin/documents?kb=${encodeURIComponent(data.doc.kb_id)}`);
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const watchedKbId = Form.useWatch("kb_id", form) ?? initialKbId ?? "";
  const watchedDocName = Form.useWatch("doc_name", form) ?? "";
  const watchedDocVersion = Form.useWatch("doc_version", form) ?? "";
  const watchedPublishedAt = Form.useWatch("published_at", form) ?? "";
  const selectedKbName = kbNameMap.get(watchedKbId) ?? "未选择";
  const selectedFileName = fileList[0]?.name ?? "未选择";

  return (
    <div className="page-stack">
      {uploadMutation.isError ? (
        <RequestErrorAlert error={normalizeApiError(uploadMutation.error)} />
      ) : null}

      <Card className="card-soft split-overview-card">
        <div className="split-overview">
          <div className="split-overview__copy">
            <div className="split-overview__label-row">
              <span className="hero-kicker">文档上传</span>
              <Typography.Text className="split-overview__eyebrow">
                把上传入口和任务监控分开，投递动作本身会更轻、更聚焦。
              </Typography.Text>
            </div>
            <Typography.Title level={3} className="hero-title">
              上传并触发入库
            </Typography.Title>
            <Typography.Paragraph className="split-overview__desc">
              左侧完成投递，右侧同步展示本次上传摘要和处理流程，页面不会因为只剩一个表单而显得空。
            </Typography.Paragraph>
            <div className="split-overview__notes">
              <span className="split-overview__note">支持按知识库定向投递</span>
              <span className="split-overview__note">任务跟踪回到管理页统一查看</span>
            </div>
          </div>
          <div className="split-overview__stats">
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">知识库数量</span>
              <span className="split-overview-stat__value">{kbQuery.data?.items.length ?? 0}</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">支持格式</span>
              <span className="split-overview-stat__value">5+</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">上传后动作</span>
              <span className="split-overview-stat__value">回列表</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">默认入口</span>
              <span className="split-overview-stat__value">单文件</span>
            </div>
          </div>
        </div>
      </Card>

      <Card
        className="card-soft split-action-card"
        title={
          <Space size={8}>
            <CloudUploadOutlined />
            <span>填写上传信息</span>
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
        <div className="split-action-card__body split-action-card__body--full">
          <div className="split-create-layout">
            <div className="split-create-main">
              <div className="split-pane-copy">
                <Typography.Text className="split-pane-copy__title">先选知识库，再投递文件</Typography.Text>
                <Typography.Text className="split-pane-copy__desc">
                  上传页只保留和投递直接相关的字段，任务记录、失败重试和历史对比都回到管理页继续处理。
                </Typography.Text>
              </div>

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
                    <Tooltip title="选择文件">
                      <Button shape="circle" icon={<InboxOutlined />} aria-label="选择文件" />
                    </Tooltip>
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
                  <div className="split-actions">
                    <Button
                      onClick={() => {
                        navigate(
                          initialKbId
                            ? `/admin/documents?kb=${encodeURIComponent(initialKbId)}`
                            : "/admin/documents"
                        );
                      }}
                    >
                      取消
                    </Button>
                    <Button
                      type="primary"
                      htmlType="submit"
                      icon={<CloudUploadOutlined />}
                      loading={uploadMutation.isPending}
                    >
                      上传并入库
                    </Button>
                  </div>
                </Form.Item>
              </Form>
            </div>

            <aside className="split-create-aside">
              <section className="split-side-card">
                <Typography.Text className="split-side-card__title">投递摘要</Typography.Text>
                <div className="split-side-metrics">
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">目标知识库</span>
                    <span className="split-side-metric__value">{selectedKbName}</span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">上传文件</span>
                    <span className="split-side-metric__value">{selectedFileName}</span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">展示名称</span>
                    <span className="split-side-metric__value">
                      {watchedDocName.trim() || "沿用文件名"}
                    </span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">版本</span>
                    <span className="split-side-metric__value">
                      {watchedDocVersion.trim() || "未填写"}
                    </span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">发布日期</span>
                    <span className="split-side-metric__value">
                      {watchedPublishedAt.trim() || "未填写"}
                    </span>
                  </div>
                </div>
              </section>

              <section className="split-side-card">
                <Typography.Text className="split-side-card__title">处理流程</Typography.Text>
                <div className="split-side-list">
                  <div className="split-side-list__item">上传成功后立即创建入库任务并记录任务 ID。</div>
                  <div className="split-side-list__item">后台会继续执行解析、切分、向量化和写入索引。</div>
                  <div className="split-side-list__item">页面会自动返回文档管理页，继续查看状态和失败重试。</div>
                </div>
              </section>
            </aside>
          </div>
        </div>
      </Card>
    </div>
  );
}
