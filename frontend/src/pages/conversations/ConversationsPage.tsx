import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  List,
  Row,
  Segmented,
  Space,
  Tag,
  Typography,
  message
} from "antd";
import {
  ConversationListItem,
  ConversationMessage,
  FeedbackPayload,
  fetchConversationDetail,
  fetchConversationList,
  submitFeedback
} from "../../shared/api/modules/conversations";
import { CitationItem } from "../../shared/api/modules/ask";
import { normalizeApiError } from "../../shared/api/errors";
import { CopyableField } from "../../shared/components/CopyableField";
import { FeedbackAction } from "../../shared/components/FeedbackAction";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import { splitCitationMarkers } from "../../shared/utils/citation";

type SortOrder = "desc" | "asc";

function asCitationItems(value: unknown): CitationItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is CitationItem => {
    if (!item || typeof item !== "object") {
      return false;
    }
    const record = item as Record<string, unknown>;
    return typeof record.chunk_id === "string" && typeof record.doc_name === "string";
  });
}

function timingEntries(value: unknown): Array<readonly [string, number]> {
  if (!value || typeof value !== "object") {
    return [];
  }
  return Object.entries(value)
    .map(([key, raw]) => [key, Number(raw)] as const)
    .filter(([, num]) => Number.isFinite(num));
}

function renderContentWithMarkers(
  content: string,
  onMarkerClick: (citationId: number) => void
) {
  const chunks = splitCitationMarkers(content);

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

export function MessageCard(props: {
  item: ConversationMessage;
  submitting: boolean;
  submitted: boolean;
  onFeedbackSubmit: (messageId: string, payload: FeedbackPayload) => Promise<void>;
}) {
  const { item, submitting, submitted, onFeedbackSubmit } = props;
  const citations = asCitationItems(item.citations);
  const timing = timingEntries(item.timing);
  const [activeCitationId, setActiveCitationId] = useState<number | null>(null);
  const citationRefs = useRef<Record<number, HTMLDivElement | null>>({});

  return (
    <List.Item>
      <Space direction="vertical" style={{ width: "100%" }} size={6}>
        <Space>
          <Tag color={item.role === "user" ? "blue" : "green"}>{item.role}</Tag>
          {item.refusal ? <Tag color="warning">refusal</Tag> : null}
          <Typography.Text type="secondary">{item.created_at}</Typography.Text>
        </Space>
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          {item.role === "assistant" && citations.length
            ? renderContentWithMarkers(item.content, (citationId) => {
                setActiveCitationId(citationId);
                const target = citationRefs.current[citationId];
                if (target) {
                  target.scrollIntoView({ behavior: "smooth", block: "center" });
                }
              })
            : item.content}
        </Typography.Paragraph>
        {item.role === "assistant" ? (
          <>
            {timing.length > 0 ? (
              <Card size="small" title="耗时信息" className="card-inset">
                <Descriptions size="small" column={2} bordered>
                  {timing.map(([key, ms]) => (
                    <Descriptions.Item key={key} label={key}>
                      {ms} ms
                    </Descriptions.Item>
                  ))}
                </Descriptions>
              </Card>
            ) : null}
            {citations.length > 0 ? (
              <Card size="small" title={`引用 (${citations.length})`}>
                <Space direction="vertical" style={{ width: "100%" }}>
                  {citations.map((citation) => (
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
              </Card>
            ) : null}
            <FeedbackAction
              messageId={item.message_id}
              submitting={submitting}
              submitted={submitted}
              onSubmit={onFeedbackSubmit}
            />
          </>
        ) : null}
      </Space>
    </List.Item>
  );
}

function matchKeyword(item: ConversationListItem, keyword: string) {
  if (!keyword) {
    return true;
  }
  const target = `${item.title ?? ""} ${item.conversation_id} ${item.kb_id}`.toLowerCase();
  return target.includes(keyword.toLowerCase());
}

function sortConversations(items: ConversationListItem[], order: SortOrder) {
  return [...items].sort((left, right) => {
    const leftTime = Date.parse(left.updated_at);
    const rightTime = Date.parse(right.updated_at);
    if (Number.isNaN(leftTime) || Number.isNaN(rightTime)) {
      return 0;
    }
    return order === "desc" ? rightTime - leftTime : leftTime - rightTime;
  });
}

export function ConversationsPage() {
  const [kbId, setKbId] = useState("");
  const [keyword, setKeyword] = useState("");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [submittingFeedbackMessageId, setSubmittingFeedbackMessageId] = useState<string | null>(
    null
  );
  const [submittedFeedbackMap, setSubmittedFeedbackMap] = useState<Record<string, true>>({});

  const listQuery = useQuery({
    queryKey: ["conversation", "list", kbId],
    queryFn: async () => {
      return fetchConversationList({ kb_id: kbId || undefined, limit: 50, offset: 0 });
    }
  });

  const detailQuery = useQuery({
    queryKey: ["conversation", "detail", selectedId],
    queryFn: async () => fetchConversationDetail(selectedId as string),
    enabled: Boolean(selectedId)
  });

  const filteredItems = useMemo(() => {
    const list = listQuery.data?.items ?? [];
    const matched = list.filter((item) => matchKeyword(item, keyword));
    return sortConversations(matched, sortOrder);
  }, [keyword, listQuery.data?.items, sortOrder]);

  const selectedMessageCount = detailQuery.data?.messages.length ?? 0;
  const assistantMessageCount =
    detailQuery.data?.messages.filter((item) => item.role === "assistant").length ?? 0;

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

  return (
    <div className="page-stack">
      <Card className="hero-card">
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Typography.Title level={4} className="hero-title">
            会话运营看板
          </Typography.Title>
          <Typography.Text className="hero-desc">
            支持会话检索、按 KB 过滤、时序排序、证据联动与逐条反馈。
          </Typography.Text>
          <div className="summary-grid">
            <div className="summary-item">
              <div className="summary-item-label">会话总数</div>
              <div className="summary-item-value">{listQuery.data?.items.length ?? 0}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">筛选后会话</div>
              <div className="summary-item-value">{filteredItems.length}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">当前消息数</div>
              <div className="summary-item-value">{selectedMessageCount}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">助手消息数</div>
              <div className="summary-item-value">{assistantMessageCount}</div>
            </div>
          </div>
        </Space>
      </Card>

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card
            title="会话列表"
            className="card-soft"
            extra={
              <Space>
                <Input
                  placeholder="按 kb_id 过滤"
                  value={kbId}
                  onChange={(event) => {
                    setKbId(event.target.value.trim());
                  }}
                  style={{ width: 220 }}
                />
                <Button onClick={() => void listQuery.refetch()} loading={listQuery.isFetching}>
                  查询
                </Button>
              </Space>
            }
          >
            <Space direction="vertical" size={10} style={{ width: "100%", marginBottom: 12 }}>
              <Input
                allowClear
                placeholder="搜索标题 / 会话ID / kb_id"
                value={keyword}
                onChange={(event) => {
                  setKeyword(event.target.value);
                }}
              />
              <Segmented<SortOrder>
                value={sortOrder}
                options={[
                  { value: "desc", label: "更新时间 ↓" },
                  { value: "asc", label: "更新时间 ↑" }
                ]}
                onChange={(value) => {
                  setSortOrder(value);
                }}
              />
            </Space>

            {listQuery.isError ? (
              <RequestErrorAlert error={normalizeApiError(listQuery.error)} />
            ) : null}

            <List
              bordered
              loading={listQuery.isLoading}
              dataSource={filteredItems}
              locale={{ emptyText: "暂无会话" }}
              renderItem={(item) => (
                <List.Item
                  style={{
                    cursor: "pointer",
                    background:
                      selectedId === item.conversation_id ? "var(--bg-emphasis)" : "transparent"
                  }}
                  onClick={() => {
                    setSelectedId(item.conversation_id);
                  }}
                >
                  <Space direction="vertical" size={0}>
                    <Typography.Text strong>{item.title || "未命名会话"}</Typography.Text>
                    <Typography.Text type="secondary">{item.conversation_id}</Typography.Text>
                    <Typography.Text type="secondary">{item.updated_at}</Typography.Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="会话详情" className="card-soft">
            {!selectedId ? (
              <Typography.Text type="secondary">请先选择左侧会话。</Typography.Text>
            ) : detailQuery.isError ? (
              <RequestErrorAlert error={normalizeApiError(detailQuery.error)} />
            ) : (
              <Space direction="vertical" size={10} style={{ width: "100%" }}>
                <CopyableField label="conversation_id" value={detailQuery.data?.conversation_id} />
                <CopyableField label="request_id" value={detailQuery.data?.request_id} />
                <List
                  loading={detailQuery.isLoading}
                  dataSource={detailQuery.data?.messages ?? []}
                  locale={{ emptyText: "暂无消息" }}
                  renderItem={(item) => (
                    <MessageCard
                      item={item}
                      submitting={submittingFeedbackMessageId === item.message_id}
                      submitted={Boolean(submittedFeedbackMap[item.message_id])}
                      onFeedbackSubmit={handleFeedbackSubmit}
                    />
                  )}
                />
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
