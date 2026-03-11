import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  FilterOutlined,
  MessageOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  UserOutlined
} from "@ant-design/icons";
import {
  Button,
  Card,
  Empty,
  Input,
  List,
  Segmented,
  Select,
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
import { fetchKbList } from "../../shared/api/modules/kb";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { FeedbackAction } from "../../shared/components/FeedbackAction";
import { RefusalNextStepsCard } from "../../shared/components/RefusalNextStepsCard";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import { splitCitationMarkers } from "../../shared/utils/citation";

type SortOrder = "desc" | "asc";
type MessageFilter = "all" | "assistant" | "user";
type ListDensity = "default" | "small";

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

function summarizeConversation(item: ConversationListItem) {
  return item.last_message_preview || "暂无摘要，进入详情可查看完整消息。";
}

function renderContentWithMarkers(content: string, onMarkerClick: (citationId: number) => void) {
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
      <article
        className={item.role === "assistant" ? "conversation-message conversation-message--assistant" : "conversation-message conversation-message--user"}
      >
        <header className="conversation-message__head">
          <Space size={8} wrap>
            <Tag color={item.role === "assistant" ? "green" : "blue"}>
              {item.role === "assistant" ? "助手" : "用户"}
            </Tag>
            {item.refusal ? <Tag color="warning">拒答</Tag> : null}
            <Typography.Text type="secondary">{formatDateTime(item.created_at)}</Typography.Text>
          </Space>
        </header>

        <Typography.Paragraph className="conversation-message__content">
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
          <Space direction="vertical" style={{ width: "100%" }} size={10}>
            {item.refusal && item.refusal_reason ? (
              <Card size="small" className="card-inset" title="拒答说明">
                <Typography.Text type="secondary">{item.refusal_reason}</Typography.Text>
              </Card>
            ) : null}
            {item.refusal ? (
              <RefusalNextStepsCard
                nextSteps={Array.isArray(item.next_steps) ? item.next_steps : []}
              />
            ) : null}
            {timing.length > 0 ? (
              <Card
                size="small"
                title={
                  <Space size={8}>
                    <ClockCircleOutlined />
                    <span>耗时信息</span>
                  </Space>
                }
                className="card-inset"
              >
                <div className="ops-progress-strip">
                  {timing.map(([key, ms]) => (
                    <Tag key={key}>{key}: {ms}ms</Tag>
                  ))}
                </div>
              </Card>
            ) : null}
            {citations.length > 0 ? (
              <Card
                size="small"
                title={
                  <Space size={8}>
                    <CheckCircleOutlined />
                    <span>引用证据 ({citations.length})</span>
                  </Space>
                }
              >
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
                        {citation.source_uri ? (
                          <Typography.Link href={citation.source_uri} target="_blank" rel="noreferrer">
                            官方来源
                          </Typography.Link>
                        ) : null}
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
          </Space>
        ) : null}
      </article>
    </List.Item>
  );
}

function matchKeyword(item: ConversationListItem, keyword: string) {
  if (!keyword) {
    return true;
  }
  const target = `${item.title ?? ""} ${item.last_message_preview ?? ""}`.toLowerCase();
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
  const [messageFilter, setMessageFilter] = useState<MessageFilter>("all");
  const [listDensity, setListDensity] = useState<ListDensity>("small");
  const [submittingFeedbackMessageId, setSubmittingFeedbackMessageId] = useState<string | null>(null);
  const [submittedFeedbackMap, setSubmittedFeedbackMap] = useState<Record<string, true>>({});

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList,
    retry: false
  });

  const listQuery = useQuery({
    queryKey: ["conversation", "list", kbId, keyword],
    queryFn: async () =>
      fetchConversationList({ kb_id: kbId || undefined, limit: 80, offset: 0, keyword: keyword.trim() || undefined }),
    retry: false
  });

  const detailQuery = useQuery({
    queryKey: ["conversation", "detail", selectedId],
    queryFn: async () => fetchConversationDetail(selectedId as string),
    enabled: Boolean(selectedId),
    retry: false
  });

  useEffect(() => {
    if (selectedId) {
      return;
    }
    const first = listQuery.data?.items?.[0];
    if (first) {
      setSelectedId(first.conversation_id);
    }
  }, [listQuery.data?.items, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    const exists = (listQuery.data?.items ?? []).some((item) => item.conversation_id === selectedId);
    if (!exists) {
      setSelectedId(listQuery.data?.items?.[0]?.conversation_id ?? null);
    }
  }, [listQuery.data?.items, selectedId]);

  const kbNameMap = useMemo(
    () => new Map((kbQuery.data?.items ?? []).map((item) => [item.kb_id, item.name])),
    [kbQuery.data?.items]
  );

  const filteredItems = useMemo(() => {
    const list = listQuery.data?.items ?? [];
    const matched = list.filter((item) => matchKeyword(item, keyword));
    return sortConversations(matched, sortOrder);
  }, [keyword, listQuery.data?.items, sortOrder]);

  const selectedConversation = useMemo(
    () => filteredItems.find((item) => item.conversation_id === selectedId) ?? null,
    [filteredItems, selectedId]
  );

  const selectedMessageCount = detailQuery.data?.messages.length ?? 0;
  const assistantMessageCount = detailQuery.data?.messages.filter((item) => item.role === "assistant").length ?? 0;
  const refusalCount = detailQuery.data?.messages.filter((item) => item.refusal).length ?? 0;
  const filteredMessages = useMemo(() => {
    const items = detailQuery.data?.messages ?? [];
    if (messageFilter === "all") {
      return items;
    }
    return items.filter((item) => item.role === messageFilter);
  }, [detailQuery.data?.messages, messageFilter]);

  const feedbackMutation = useMutation({
    mutationFn: async (params: { messageId: string; payload: FeedbackPayload }) =>
      submitFeedback(params.messageId, params.payload),
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
      message.error(formatApiErrorMessage(normalized));
      throw error;
    } finally {
      setSubmittingFeedbackMessageId((current) => (current === messageId ? null : current));
    }
  };

  return (
    <div className="page-stack">
      <Card className="hero-card">
        <div className="hero-layout">
          <Space direction="vertical" size={10} style={{ width: "100%" }}>
            <span className="hero-kicker">Conversation Ops</span>
            <Typography.Title level={4} className="hero-title">
              会话运营台
            </Typography.Title>
            <Typography.Text className="hero-desc">
              回看用户提问路径、复核证据引用与反馈质量。默认界面只保留业务信息，不把内部 ID 暴露成主视图内容。
            </Typography.Text>
            <div className="hero-note">
              <span className="hero-note__item">按知识库名称筛选</span>
              <span className="hero-note__item">会话摘要直接预览</span>
              <span className="hero-note__item">证据与反馈在消息内完成复核</span>
            </div>
          </Space>
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
              <div className="summary-item-label">拒答消息</div>
              <div className="summary-item-value">{refusalCount}</div>
            </div>
          </div>
        </div>
      </Card>

      <div className="ops-workbench">
        <Card
          title={
            <Space size={8}>
              <MessageOutlined />
              <span>会话列表</span>
            </Space>
          }
          className="card-soft ops-pane-card"
          extra={
            <Button icon={<ReloadOutlined />} onClick={() => void listQuery.refetch()} loading={listQuery.isFetching}>
              刷新
            </Button>
          }
        >
          <div className="ops-pane-body">
            <div className="density-toolbar">
              <Space wrap>
                <Select
                  allowClear
                  showSearch
                  value={kbId || undefined}
                  placeholder="按知识库筛选"
                  optionFilterProp="label"
                  style={{ width: 220 }}
                  options={(kbQuery.data?.items ?? []).map((item) => ({
                    value: item.kb_id,
                    label: item.name
                  }))}
                  onChange={(value) => {
                    setKbId(typeof value === "string" ? value : "");
                  }}
                />
                <Input
                  allowClear
                  prefix={<SearchOutlined />}
                  placeholder="搜索标题或摘要"
                  value={keyword}
                  onChange={(event) => {
                    setKeyword(event.target.value);
                  }}
                  style={{ width: 240 }}
                />
              </Space>
              <Segmented<SortOrder>
                value={sortOrder}
                options={[
                  { value: "desc", label: "最近更新" },
                  { value: "asc", label: "最早更新" }
                ]}
                onChange={(value) => {
                  setSortOrder(value);
                }}
              />
            </div>

            {listQuery.isError ? <RequestErrorAlert error={normalizeApiError(listQuery.error)} /> : null}

            <div className="ops-scroll-pane">
              {listQuery.isLoading ? (
                <Card className="card-inset">
                  <Typography.Text type="secondary">会话列表加载中...</Typography.Text>
                </Card>
              ) : filteredItems.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选下暂无会话" />
              ) : (
                <List
                  size={listDensity}
                  dataSource={filteredItems}
                  renderItem={(item) => (
                    <List.Item>
                      <button
                        type="button"
                        className={selectedId === item.conversation_id ? "conversation-list-item conversation-list-item--active" : "conversation-list-item"}
                        onClick={() => {
                          setSelectedId(item.conversation_id);
                        }}
                      >
                        <div className="conversation-list-item__head">
                          <Typography.Text strong>{item.title || "未命名会话"}</Typography.Text>
                          <Tag>{formatDateTime(item.updated_at)}</Tag>
                        </div>
                        <Typography.Paragraph className="conversation-list-item__preview">
                          {summarizeConversation(item)}
                        </Typography.Paragraph>
                        <div className="conversation-list-item__meta">
                          <Tag color="geekblue">{kbNameMap.get(item.kb_id) ?? "未命名知识库"}</Tag>
                          {item.last_message_at ? <span>最近消息 {formatDateTime(item.last_message_at)}</span> : null}
                        </div>
                      </button>
                    </List.Item>
                  )}
                />
              )}
            </div>
          </div>
        </Card>

        <Card
          title={
            <Space size={8}>
              <FilterOutlined />
              <span>会话详情</span>
            </Space>
          }
          className="card-soft ops-pane-card"
          extra={
            selectedId ? (
              <Button icon={<ReloadOutlined />} onClick={() => void detailQuery.refetch()} loading={detailQuery.isFetching}>
                刷新详情
              </Button>
            ) : null
          }
        >
          <div className="ops-pane-body">
            {!selectedId ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请先选择左侧会话。" />
            ) : detailQuery.isError ? (
              <RequestErrorAlert error={normalizeApiError(detailQuery.error)} />
            ) : (
              <div className="ops-scroll-pane">
                <Space direction="vertical" size={12} style={{ width: "100%" }}>
                  <div className="ops-pane-intro">
                    <Typography.Text className="ops-pane-intro__title">
                      {selectedConversation?.title || "未命名会话"}
                    </Typography.Text>
                    <Typography.Text className="ops-pane-intro__desc">
                      {selectedConversation
                        ? `所属知识库：${kbNameMap.get(selectedConversation.kb_id) ?? "未命名知识库"}`
                        : "查看用户消息、助手回答、引用证据与反馈情况。"}
                    </Typography.Text>
                  </div>

                  <div className="density-toolbar">
                    <Space wrap>
                      <Tag icon={<MessageOutlined />}>消息 {selectedMessageCount}</Tag>
                      <Tag color="processing" icon={<RobotOutlined />}>助手 {assistantMessageCount}</Tag>
                      <Tag color="warning" icon={<UserOutlined />}>拒答 {refusalCount}</Tag>
                    </Space>
                    <Space>
                      <Segmented<MessageFilter>
                        size="small"
                        value={messageFilter}
                        options={[
                          { label: "全部", value: "all" },
                          { label: "仅助手", value: "assistant" },
                          { label: "仅用户", value: "user" }
                        ]}
                        onChange={(value) => {
                          setMessageFilter(value);
                        }}
                      />
                      <Segmented<ListDensity>
                        size="small"
                        value={listDensity}
                        options={[
                          { label: "舒适", value: "default" },
                          { label: "紧凑", value: "small" }
                        ]}
                        onChange={(value) => {
                          setListDensity(value);
                        }}
                      />
                    </Space>
                  </div>

                  {detailQuery.isLoading ? (
                    <Card className="card-inset">
                      <Typography.Text type="secondary">会话详情加载中...</Typography.Text>
                    </Card>
                  ) : filteredMessages.length === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选下暂无消息" />
                  ) : (
                    <List
                      size={listDensity}
                      dataSource={filteredMessages}
                      renderItem={(item) => (
                        <MessageCard
                          item={item}
                          submitting={submittingFeedbackMessageId === item.message_id}
                          submitted={Boolean(submittedFeedbackMap[item.message_id])}
                          onFeedbackSubmit={handleFeedbackSubmit}
                        />
                      )}
                    />
                  )}
                </Space>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
