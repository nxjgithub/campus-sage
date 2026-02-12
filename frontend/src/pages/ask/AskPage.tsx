import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Tag,
  Typography,
  message
} from "antd";
import { askByKb, AskResponse } from "../../shared/api/modules/ask";
import { fetchDocuments } from "../../shared/api/modules/documents";
import { FeedbackPayload, submitFeedback } from "../../shared/api/modules/conversations";
import { fetchKbList } from "../../shared/api/modules/kb";
import { normalizeApiError } from "../../shared/api/errors";
import { CopyableField } from "../../shared/components/CopyableField";
import { FeedbackAction } from "../../shared/components/FeedbackAction";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import { splitCitationMarkers } from "../../shared/utils/citation";

interface AskFormValues {
  kb_id: string;
  question: string;
  conversation_id?: string;
  doc_ids?: string[];
  topk?: number;
  threshold?: number;
  rerank_enabled?: boolean;
  debug?: boolean;
}

interface AskPageProps {
  initialResult?: AskResponse | null;
}

const QUESTION_TEMPLATES = [
  "补考申请需要满足什么条件？",
  "转专业的时间窗口与流程是什么？",
  "奖学金评审主要依据有哪些？"
];

function renderAnswerWithCitationLinks(
  answer: string,
  onMarkerClick: (citationId: number) => void
) {
  const chunks = splitCitationMarkers(answer);

  return chunks.map((chunk, index) => {
    if (chunk.type === "text") {
      return <span key={`text_${index}`}>{chunk.value}</span>;
    }
    return (
      <span
        key={`marker_${index}`}
        className="answer-marker"
        onClick={() => onMarkerClick(chunk.citationId)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onMarkerClick(chunk.citationId);
          }
        }}
        role="button"
        tabIndex={0}
      >
        {chunk.marker}
      </span>
    );
  });
}

export function AskPage({ initialResult = null }: AskPageProps) {
  const [result, setResult] = useState<AskResponse | null>(initialResult);
  const [activeCitationId, setActiveCitationId] = useState<number | null>(null);
  const [submittingFeedbackMessageId, setSubmittingFeedbackMessageId] = useState<string | null>(
    null
  );
  const [submittedFeedbackMap, setSubmittedFeedbackMap] = useState<Record<string, true>>({});
  const citationRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const [form] = Form.useForm<AskFormValues>();
  const selectedKbId = Form.useWatch("kb_id", form);

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList
  });

  const documentsQuery = useQuery({
    queryKey: ["documents", "ask-filter", selectedKbId],
    queryFn: async () => fetchDocuments(selectedKbId as string),
    enabled: Boolean(selectedKbId)
  });

  const askMutation = useMutation({
    mutationFn: async (values: AskFormValues) => {
      return askByKb(values.kb_id, {
        question: values.question,
        conversation_id: values.conversation_id,
        topk: values.topk,
        threshold: values.threshold,
        rerank_enabled: values.rerank_enabled,
        filters: values.doc_ids?.length ? { doc_ids: values.doc_ids } : undefined,
        debug: values.debug
      });
    },
    onSuccess: (data) => {
      setResult(data);
      setActiveCitationId(null);
      if (data.refusal) {
        message.warning("当前问题触发拒答，请查看建议与引用信息");
      }
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  const answerContent = useMemo(() => {
    if (!result?.answer) {
      return null;
    }
    return renderAnswerWithCitationLinks(result.answer, (citationId) => {
      setActiveCitationId(citationId);
      const target = citationRefs.current[citationId];
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  }, [result?.answer]);

  useEffect(() => {
    if (!activeCitationId) {
      return;
    }
    const target = citationRefs.current[activeCitationId];
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [activeCitationId]);

  const feedbackMutation = useMutation({
    mutationFn: async (params: { messageId: string; payload: FeedbackPayload }) => {
      return submitFeedback(params.messageId, params.payload);
    },
    retry: false
  });

  const handleFeedbackSubmit = async (messageId: string, payload: FeedbackPayload) => {
    setSubmittingFeedbackMessageId(messageId);
    try {
      await feedbackMutation.mutateAsync({ messageId, payload });
      setSubmittedFeedbackMap((previous) => ({
        ...previous,
        [messageId]: true
      }));
      message.success("反馈已提交");
    } catch (error) {
      const normalized = normalizeApiError(error);
      message.error(`${normalized.message}（${normalized.code}）`);
      throw error;
    } finally {
      setSubmittingFeedbackMessageId((current) => (current === messageId ? null : current));
    }
  };

  const summaryItems = [
    {
      label: "可用知识库",
      value: kbQuery.data?.items.length ?? 0
    },
    {
      label: "文档过滤候选",
      value: documentsQuery.data?.items.length ?? 0
    },
    {
      label: "本次引用数",
      value: result?.citations.length ?? 0
    },
    {
      label: "拒答状态",
      value: result?.refusal ? "是" : "否"
    }
  ];

  return (
    <div className="page-stack">
      <Card className="hero-card">
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Typography.Title level={4} className="hero-title">
            真实业务问答工作台
          </Typography.Title>
          <Typography.Text className="hero-desc">
            支持 KB 指定、文档过滤、对话连续追问、引用定位与答案反馈闭环。
          </Typography.Text>
          <div className="summary-grid">
            {summaryItems.map((item) => (
              <div className="summary-item" key={item.label}>
                <div className="summary-item-label">{item.label}</div>
                <div className="summary-item-value">{item.value}</div>
              </div>
            ))}
          </div>
        </Space>
      </Card>

      <Row gutter={16}>
        <Col xs={24} lg={11}>
          <Card title="发起问答" className="card-soft">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Alert
                type="info"
                showIcon
                message="建议先选择知识库，再根据问题范围追加文档过滤。"
              />
              <div className="card-inset" style={{ padding: 10 }}>
                <Typography.Text type="secondary">快捷问题模板</Typography.Text>
                <Space wrap style={{ marginTop: 8 }}>
                  {QUESTION_TEMPLATES.map((question) => (
                    <Button
                      size="small"
                      key={question}
                      onClick={() => {
                        form.setFieldValue("question", question);
                      }}
                    >
                      {question}
                    </Button>
                  ))}
                </Space>
              </div>
            </Space>

            {askMutation.isError ? (
              <RequestErrorAlert error={normalizeApiError(askMutation.error)} />
            ) : null}
            {documentsQuery.isError ? (
              <RequestErrorAlert error={normalizeApiError(documentsQuery.error)} />
            ) : null}

            <Form<AskFormValues>
              form={form}
              layout="vertical"
              style={{ marginTop: 12 }}
              onFinish={(values) => {
                askMutation.mutate(values);
              }}
            >
              <Form.Item
                name="kb_id"
                label="知识库"
                rules={[{ required: true, message: "请选择或输入知识库 ID" }]}
              >
                <AutoComplete
                  options={(kbQuery.data?.items ?? []).map((item) => ({
                    value: item.kb_id,
                    label: `${item.name} (${item.kb_id})`
                  }))}
                  placeholder="请选择或手动输入 kb_id"
                  notFoundContent={kbQuery.isLoading ? "知识库加载中..." : "无可选知识库"}
                  filterOption={(inputValue, option) => {
                    if (!option?.label) {
                      return false;
                    }
                    return String(option.label).toLowerCase().includes(inputValue.toLowerCase());
                  }}
                />
              </Form.Item>
              <Form.Item
                name="question"
                label="问题"
                rules={[{ required: true, message: "请输入问题" }]}
              >
                <Input.TextArea rows={5} placeholder="例如：补考申请需要满足什么条件？" />
              </Form.Item>
              <Form.Item name="conversation_id" label="会话 ID（可选）">
                <Input placeholder="可填写已有 conversation_id 进行连续问答" />
              </Form.Item>
              <Form.Item name="doc_ids" label="限定文档（可选）">
                <Select
                  mode="multiple"
                  allowClear
                  loading={documentsQuery.isLoading}
                  placeholder="可选择一个或多个文档进行过滤"
                  options={(documentsQuery.data?.items ?? []).map((item) => ({
                    label: `${item.doc_name} (${item.doc_id})`,
                    value: item.doc_id
                  }))}
                />
              </Form.Item>

              <Card size="small" className="card-inset" title="高级参数">
                <Space wrap>
                  <Form.Item name="topk" label="TopK">
                    <InputNumber min={1} />
                  </Form.Item>
                  <Form.Item name="threshold" label="阈值">
                    <InputNumber min={0} max={1} step={0.01} />
                  </Form.Item>
                  <Form.Item name="rerank_enabled" label="重排">
                    <Select
                      allowClear
                      options={[
                        { value: true, label: "true" },
                        { value: false, label: "false" }
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="debug" label="Debug">
                    <Select
                      allowClear
                      options={[
                        { value: true, label: "true" },
                        { value: false, label: "false" }
                      ]}
                    />
                  </Form.Item>
                </Space>
              </Card>

              <Form.Item style={{ marginTop: 12 }}>
                <Button type="primary" htmlType="submit" loading={askMutation.isPending}>
                  提问
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={13}>
          <Card title="回答与证据" className="card-soft">
            {!result ? (
              <Empty description="尚未发起问答" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Space wrap>
                  <Tag color={result.refusal ? "warning" : "success"}>
                    {result.refusal ? "拒答" : "已回答"}
                  </Tag>
                  {result.refusal_reason ? <Tag>{result.refusal_reason}</Tag> : null}
                </Space>

                <Typography.Paragraph className="answer-block">
                  {answerContent}
                </Typography.Paragraph>

                {result.suggestions?.length ? (
                  <Card size="small" title="下一步建议" className="card-inset">
                    <ul className="muted-list">
                      {result.suggestions.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </Card>
                ) : null}

                <Card size="small" title={`引用 (${result.citations.length})`}>
                  {result.citations.length === 0 ? (
                    <Typography.Text type="secondary">当前回答未返回引用。</Typography.Text>
                  ) : (
                    <Space direction="vertical" style={{ width: "100%" }}>
                      {result.citations.map((citation) => (
                        <Card
                          key={citation.chunk_id}
                          size="small"
                          className={
                            citation.citation_id === activeCitationId
                              ? "citation-card citation-card--active"
                              : "citation-card"
                          }
                        >
                          <div
                            ref={(node) => {
                              citationRefs.current[citation.citation_id] = node;
                            }}
                          />
                          <Space direction="vertical" size={4}>
                            <Typography.Text strong>
                              [{citation.citation_id}] {citation.doc_name}
                            </Typography.Text>
                            <Typography.Text type="secondary">
                              {citation.section_path
                                ? `章节：${citation.section_path}`
                                : `页码：${citation.page_start ?? "-"}-${
                                    citation.page_end ?? citation.page_start ?? "-"
                                  }`}
                            </Typography.Text>
                            <Typography.Paragraph style={{ marginBottom: 0 }}>
                              {citation.snippet}
                            </Typography.Paragraph>
                          </Space>
                        </Card>
                      ))}
                    </Space>
                  )}
                </Card>

                <Divider style={{ margin: "6px 0" }} />
                {result.message_id ? (
                  <FeedbackAction
                    messageId={result.message_id}
                    submitting={submittingFeedbackMessageId === result.message_id}
                    submitted={Boolean(submittedFeedbackMap[result.message_id])}
                    onSubmit={handleFeedbackSubmit}
                  />
                ) : null}
                <CopyableField label="conversation_id" value={result.conversation_id} />
                <CopyableField label="message_id" value={result.message_id} />
                <CopyableField label="request_id" value={result.request_id} />
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
