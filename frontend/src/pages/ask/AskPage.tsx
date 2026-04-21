import { useEffect, useMemo, useRef, useState } from "react";
import { DeleteOutlined, EditOutlined, HistoryOutlined, LoginOutlined, LogoutOutlined, MessageOutlined, PlusOutlined, SearchOutlined, SendOutlined, StopOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Select,
  Skeleton,
  Space,
  Tag,
  Tooltip,
  Typography,
  message
} from "antd";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  AskStreamDoneData,
  AskStreamErrorData,
  AskStreamEvent,
  NextStepItem,
  AskStreamRefusalData,
  AskStreamStartData,
  AskStreamTokenData,
  CitationItem,
  askStreamByKb,
  cancelChatRun,
  editAndResendMessage,
  getChatRun,
  regenerateMessage
} from "../../shared/api/modules/ask";
import {
  ConversationListItem,
  ConversationMessage,
  createConversation,
  deleteConversation,
  fetchConversationList,
  fetchConversationMessagesPage,
  renameConversation,
  submitFeedback
} from "../../shared/api/modules/conversations";
import { fetchKbList } from "../../shared/api/modules/kb";
import {
  ApiErrorShape,
  formatApiErrorMessage,
  normalizeApiError
} from "../../shared/api/errors";
import { useAuth } from "../../shared/auth/auth";
import { getAccessToken } from "../../shared/auth/token";
import { FeedbackAction } from "../../shared/components/FeedbackAction";
import { PortalSwitch } from "../../shared/components/PortalSwitch";
import { RefusalNextStepsCard } from "../../shared/components/RefusalNextStepsCard";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import { splitCitationMarkers } from "../../shared/utils/citation";

type ComposerStatus = "idle" | "sending" | "streaming" | "stopping" | "failed";

interface ThreadMessage {
  local_id: string;
  message_id: string | null;
  role: "user" | "assistant";
  content: string;
  citations: CitationItem[];
  refusal: boolean | null;
  refusal_reason: string | null;
  suggestions: string[];
  next_steps: NextStepItem[];
  timing: Record<string, number> | null;
  created_at: string;
  request_id: string | null;
  pending: boolean;
}

const MESSAGE_PAGE_SIZE = 30;
const COMPOSER_STATUS_LABEL: Record<ComposerStatus, string> = {
  idle: "就绪",
  sending: "发送中",
  streaming: "生成中",
  stopping: "停止中",
  failed: "发送失败"
};

const COMPOSER_STATUS_COLOR: Record<ComposerStatus, string> = {
  idle: "default",
  sending: "processing",
  streaming: "blue",
  stopping: "warning",
  failed: "error"
};

const QUESTION_STARTERS = [
  "研究生复试需要准备哪些材料？",
  "补考申请有哪些条件和流程？",
  "奖学金评定通常参考哪些要求？"
];

const COMPOSER_SHORTCUTS = [
  { label: "复试材料", value: QUESTION_STARTERS[0] },
  { label: "补考流程", value: QUESTION_STARTERS[1] },
  { label: "奖学金要求", value: QUESTION_STARTERS[2] }
];

const QUALITY_PROMISES = [
  { label: "证据定位", value: "文档名、页码或章节、片段" },
  { label: "拒答边界", value: "证据不足时给出下一步建议" },
  { label: "过程回放", value: "会话、引用、反馈可追踪" }
];

function toThreadMessage(item: ConversationMessage): ThreadMessage {
  return {
    local_id: `server_${item.message_id}`,
    message_id: item.message_id,
    role: item.role,
    content: item.content,
    citations: Array.isArray(item.citations) ? item.citations : [],
    refusal: item.refusal ?? null,
    refusal_reason: item.refusal_reason ?? null,
    suggestions: [],
    next_steps: Array.isArray(item.next_steps) ? item.next_steps : [],
    timing: item.timing ?? null,
    created_at: item.created_at,
    request_id: null,
    pending: false
  };
}

function mergeMessages(history: ThreadMessage[], local: ThreadMessage[]) {
  if (!local.length) {
    return history;
  }
  const historyIds = new Set(
    history.map((item) => item.message_id).filter((item): item is string => Boolean(item))
  );
  const pending = local.filter((item) => !item.message_id || !historyIds.has(item.message_id));
  return [...history, ...pending];
}

function messageKey(item: ThreadMessage) {
  return item.message_id ?? item.local_id;
}

function nowIsoString() {
  return new Date().toISOString();
}

function buildDraftFromNextStep(step: NextStepItem, currentQuestion: string) {
  const trimmedQuestion = currentQuestion.trim();
  const value = step.value?.trim() ?? "";

  if (step.action === "rewrite_question") {
    return value || trimmedQuestion;
  }
  if (step.action === "search_keyword") {
    return value ? `${trimmedQuestion || "请根据以下关键词帮助我检索"}：${value}` : trimmedQuestion;
  }
  if (step.action === "add_context") {
    if (trimmedQuestion && value) {
      return `${trimmedQuestion}\n补充信息：${value}`;
    }
    return value || trimmedQuestion;
  }
  return value || trimmedQuestion;
}

function isOfficialSourceUrl(value?: string | null) {
  if (!value) {
    return false;
  }
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function resolveOfficialSourceUrl(step: NextStepItem, citations: CitationItem[]) {
  if (isOfficialSourceUrl(step.value)) {
    return step.value as string;
  }
  const candidate = citations.find((citation) => isOfficialSourceUrl(citation.source_uri));
  return candidate?.source_uri ?? null;
}

function compactTime(iso?: string | null) {
  if (!iso) {
    return "-";
  }
  const time = new Date(iso);
  if (Number.isNaN(time.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(time);
}

function renderWithMarkers(text: string, onMarkerClick: (citationId: number) => void) {
  const parts = splitCitationMarkers(text);
  return parts.map((part, index) => {
    if (part.type === "text") {
      return <span key={`text_${index}`}>{part.value}</span>;
    }
    return (
      <span
        key={`marker_${index}`}
        className="answer-marker"
        tabIndex={0}
        role="button"
        onClick={(event) => {
          event.stopPropagation();
          onMarkerClick(part.citationId);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            event.stopPropagation();
            onMarkerClick(part.citationId);
          }
        }}
      >
        {part.marker}
      </span>
    );
  });
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function summarizeConversation(item: ConversationListItem) {
  return item.last_message_preview || "暂无消息";
}

export function AskPage() {
  const navigate = useNavigate();
  const { user, role, isAuthenticated, signOut } = useAuth();
  const hasAccessToken = Boolean(getAccessToken());
  const [kbId, setKbId] = useState("");
  const [keyword, setKeyword] = useState("");
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [historyMessages, setHistoryMessages] = useState<ThreadMessage[]>([]);
  const [localMessages, setLocalMessages] = useState<ThreadMessage[]>([]);
  const [messagesHasMore, setMessagesHasMore] = useState(false);
  const [messagesBefore, setMessagesBefore] = useState<string | null>(null);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesError, setMessagesError] = useState<ApiErrorShape | null>(null);
  const [composerText, setComposerText] = useState("");
  const [composerStatus, setComposerStatus] = useState<ComposerStatus>("idle");
  const [streamRunId, setStreamRunId] = useState<string | null>(null);
  const [streamController, setStreamController] = useState<AbortController | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [activeAssistantKey, setActiveAssistantKey] = useState<string | null>(null);
  const [activeCitationId, setActiveCitationId] = useState<number | null>(null);
  const [threadError, setThreadError] = useState<ApiErrorShape | null>(null);
  const [submittingFeedbackMessageId, setSubmittingFeedbackMessageId] = useState<string | null>(
    null
  );
  const [submittedFeedbackMap, setSubmittedFeedbackMap] = useState<Record<string, true>>({});
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameTitle, setRenameTitle] = useState("");
  const [renameLoading, setRenameLoading] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editQuestion, setEditQuestion] = useState("");
  const [editTargetMessageId, setEditTargetMessageId] = useState<string | null>(null);
  const [actioningMessageId, setActioningMessageId] = useState<string | null>(null);
  const threadViewportRef = useRef<HTMLDivElement | null>(null);
  const citationRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const currentUserLocalIdRef = useRef<string | null>(null);
  const currentAssistantLocalIdRef = useRef<string | null>(null);

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList,
    retry: false
  });

  const conversationQuery = useQuery({
    queryKey: ["chat", "conversation-list", hasAccessToken, kbId, keyword],
    queryFn: () =>
      fetchConversationList({
        kb_id: kbId || undefined,
        keyword: keyword.trim() || undefined,
        limit: 60
      }),
    enabled: hasAccessToken,
    retry: false
  });

  const conversationItems = useMemo(
    () => conversationQuery.data?.items ?? [],
    [conversationQuery.data?.items]
  );
  const activeConversation = useMemo(
    () =>
      conversationItems.find((item) => item.conversation_id === activeConversationId) ?? null,
    [activeConversationId, conversationItems]
  );

  useEffect(() => {
    if (kbId || !kbQuery.data?.items.length) {
      return;
    }
    setKbId(kbQuery.data.items[0].kb_id);
  }, [kbId, kbQuery.data?.items]);

  useEffect(() => {
    if (!hasAccessToken || activeConversationId || !conversationItems.length) {
      return;
    }
    setActiveConversationId(conversationItems[0].conversation_id);
  }, [activeConversationId, conversationItems, hasAccessToken]);

  const threadMessages = useMemo(
    () => mergeMessages(historyMessages, localMessages),
    [historyMessages, localMessages]
  );

  useEffect(() => {
    if (!historyMessages.length || !localMessages.length) {
      return;
    }
    const ids = new Set(
      historyMessages
        .map((item) => item.message_id)
        .filter((item): item is string => Boolean(item))
    );
    setLocalMessages((previous) => {
      const next = previous.filter((item) => !item.message_id || !ids.has(item.message_id));
      if (next.length === previous.length) {
        return previous;
      }
      return next;
    });
  }, [historyMessages, localMessages.length]);

  const assistantMessages = useMemo(
    () => threadMessages.filter((item) => item.role === "assistant"),
    [threadMessages]
  );

  useEffect(() => {
    if (!assistantMessages.length) {
      setActiveAssistantKey(null);
      return;
    }
    if (activeAssistantKey && assistantMessages.some((item) => messageKey(item) === activeAssistantKey)) {
      return;
    }
    setActiveAssistantKey(messageKey(assistantMessages[assistantMessages.length - 1]));
  }, [activeAssistantKey, assistantMessages]);

  const selectedAssistant = useMemo(() => {
    if (!assistantMessages.length) {
      return null;
    }
    const matched = assistantMessages.find((item) => messageKey(item) === activeAssistantKey);
    return matched ?? assistantMessages[assistantMessages.length - 1];
  }, [activeAssistantKey, assistantMessages]);
  const selectedAssistantCitationCount = selectedAssistant?.citations.length ?? 0;

  const answeredCount = useMemo(
    () => assistantMessages.filter((item) => !item.refusal && !item.pending).length,
    [assistantMessages]
  );

  const refusedCount = useMemo(
    () => assistantMessages.filter((item) => Boolean(item.refusal)).length,
    [assistantMessages]
  );

  const pendingCount = useMemo(
    () => assistantMessages.filter((item) => item.pending).length,
    [assistantMessages]
  );

  const citedAnswerCount = useMemo(
    () => assistantMessages.filter((item) => item.citations.length > 0).length,
    [assistantMessages]
  );

  const totalCitationCount = useMemo(
    () => assistantMessages.reduce((sum, item) => sum + item.citations.length, 0),
    [assistantMessages]
  );

  const citationCoverage = useMemo(() => {
    if (!assistantMessages.length) {
      return 0;
    }
    return Math.round((citedAnswerCount / assistantMessages.length) * 100);
  }, [assistantMessages.length, citedAnswerCount]);

  const latestAssistantContent = assistantMessages[assistantMessages.length - 1]?.content ?? "";

  useEffect(() => {
    const container = threadViewportRef.current;
    if (!container) {
      return;
    }
    container.scrollTop = container.scrollHeight;
  }, [threadMessages.length, latestAssistantContent, composerStatus]);

  useEffect(() => {
    if (!evidenceOpen || !selectedAssistant || activeCitationId === null) {
      return;
    }
    const key = `${messageKey(selectedAssistant)}_${activeCitationId}`;
    const node = citationRefs.current[key];
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [activeCitationId, evidenceOpen, selectedAssistant]);

  useEffect(() => {
    if (!evidenceOpen) {
      return;
    }
    const onKeyDown = () => {
      setEvidenceOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [evidenceOpen]);

  const feedbackMutation = useMutation({
    mutationFn: (params: {
      messageId: string;
      payload: { rating: "up" | "down"; reasons: string[]; comment?: string; expected_hint?: string };
    }) => submitFeedback(params.messageId, params.payload),
    retry: false
  });

  const regenerateMutation = useMutation({
    mutationFn: (messageId: string) => regenerateMessage(messageId),
    retry: false
  });

  const editResendMutation = useMutation({
    mutationFn: (params: { messageId: string; question: string }) =>
      editAndResendMessage(params.messageId, {
        question: params.question
      }),
    retry: false
  });

  const createConversationMutation = useMutation({
    mutationFn: createConversation,
    retry: false
  });

  const renameConversationMutation = useMutation({
    mutationFn: (params: { conversationId: string; title: string }) =>
      renameConversation(params.conversationId, { title: params.title }),
    retry: false
  });

  const deleteConversationMutation = useMutation({
    mutationFn: deleteConversation,
    retry: false
  });

  const isBusy =
    composerStatus === "sending" ||
    composerStatus === "streaming" ||
    composerStatus === "stopping";

  const refreshConversationList = async () => {
    if (!hasAccessToken) {
      return;
    }
    await conversationQuery.refetch();
  };

  const loadMessages = async (conversationId: string, appendOlder: boolean) => {
    setMessagesLoading(true);
    try {
      const response = await fetchConversationMessagesPage(conversationId, {
        before: appendOlder ? messagesBefore ?? undefined : undefined,
        limit: MESSAGE_PAGE_SIZE
      });
      const mapped = response.items.map(toThreadMessage);
      setHistoryMessages((previous) => (appendOlder ? [...mapped, ...previous] : mapped));
      setMessagesHasMore(response.has_more);
      setMessagesBefore(response.next_before ?? null);
      setMessagesError(null);
    } catch (error) {
      setMessagesError(normalizeApiError(error));
    } finally {
      setMessagesLoading(false);
    }
  };

  useEffect(() => {
    if (!hasAccessToken || !activeConversationId) {
      setHistoryMessages([]);
      setMessagesBefore(null);
      setMessagesHasMore(false);
      return;
    }
    void loadMessages(activeConversationId, false);
    // 会话切换时只按 activeConversationId 触发初始化加载。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConversationId, hasAccessToken]);

  const patchLocalAssistant = (
    localId: string,
    patch:
      | Partial<ThreadMessage>
      | ((current: ThreadMessage) => Partial<ThreadMessage> | ThreadMessage)
  ) => {
    setLocalMessages((previous) =>
      previous.map((item) => {
        if (item.local_id !== localId) {
          return item;
        }
        if (typeof patch === "function") {
          const next = patch(item);
          if ("local_id" in next) {
            return next as ThreadMessage;
          }
          return { ...item, ...(next as Partial<ThreadMessage>) };
        }
        return { ...item, ...patch };
      })
    );
  };

  const patchLocalUserMessageId = (localId: string, messageId?: string | null) => {
    if (!messageId) {
      return;
    }
    setLocalMessages((previous) =>
      previous.map((item) =>
        item.local_id === localId
          ? {
              ...item,
              message_id: messageId
            }
          : item
      )
    );
  };

  const recoverRun = async (runId: string) => {
    try {
      const run = await getChatRun(runId);
      if (run.conversation_id) {
        setActiveConversationId(run.conversation_id);
        if (hasAccessToken) {
          await loadMessages(run.conversation_id, false);
        }
      }
      await refreshConversationList();
    } catch {
      return;
    }
  };

  const applyStreamEvent = (
    event: AskStreamEvent,
    runtime: { userLocalId: string; assistantLocalId: string; setConversation: (id: string) => void }
  ) => {
    if (event.event === "start") {
      const data = event.data as AskStreamStartData;
      setStreamRunId(data.run_id);
      setComposerStatus("streaming");
      if (data.conversation_id) {
        runtime.setConversation(data.conversation_id);
      }
      return;
    }
    if (event.event === "token") {
      const data = event.data as AskStreamTokenData;
      patchLocalAssistant(runtime.assistantLocalId, (current) => ({
        content: `${current.content}${data.delta}`,
        request_id: data.request_id ?? current.request_id,
        pending: true
      }));
      return;
    }
    if (event.event === "citation") {
      patchLocalAssistant(runtime.assistantLocalId, (current) => ({
        citations: [...current.citations, event.data.citation]
      }));
      return;
    }
    if (event.event === "refusal") {
      const data = event.data as AskStreamRefusalData;
      patchLocalUserMessageId(runtime.userLocalId, data.user_message_id);
      patchLocalAssistant(runtime.assistantLocalId, {
        message_id: data.message_id ?? null,
        content: data.answer,
        refusal: true,
        refusal_reason: data.refusal_reason ?? null,
        suggestions: data.suggestions ?? [],
        next_steps: data.next_steps ?? [],
        timing: data.timing ?? null,
        created_at: data.assistant_created_at ?? nowIsoString(),
        request_id: data.request_id ?? null,
        pending: false
      });
      if (data.conversation_id) {
        runtime.setConversation(data.conversation_id);
      }
      return;
    }
    if (event.event === "error") {
      const data = event.data as AskStreamErrorData;
      if (data.code === "CHAT_RUN_CANCELED") {
        patchLocalAssistant(runtime.assistantLocalId, (current) => ({
          content: current.content || "已取消生成。",
          pending: false,
          request_id: data.request_id ?? current.request_id
        }));
        return;
      }
      setThreadError({
        code: data.code,
        message: data.message,
        detail: data.detail,
        request_id: data.request_id ?? null
      });
      patchLocalAssistant(runtime.assistantLocalId, (current) => ({
        content: current.content || `生成失败：${data.message}`,
        pending: false
      }));
      return;
    }
    if (event.event === "done") {
      const data = event.data as AskStreamDoneData;
      patchLocalUserMessageId(runtime.userLocalId, data.user_message_id);
      patchLocalAssistant(runtime.assistantLocalId, (current) => ({
        message_id: data.message_id ?? current.message_id,
        created_at: data.assistant_created_at ?? current.created_at,
        timing: data.timing ?? current.timing,
        refusal: data.refusal ?? current.refusal,
        request_id: data.request_id ?? current.request_id,
        pending: false,
        content: data.status === "canceled" && !current.content ? "已取消生成。" : current.content
      }));
      if (data.conversation_id) {
        runtime.setConversation(data.conversation_id);
      }
      setStreamRunId(null);
      setComposerStatus(data.status === "failed" ? "failed" : "idle");
    }
  };

  const handleSend = async () => {
    const question = composerText.trim();
    const finalKbId = kbId.trim();
    if (!question) {
      message.warning("请输入问题");
      return;
    }
    if (!finalKbId) {
      message.warning("请选择知识库");
      return;
    }
    const seed = `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
    const userLocalId = `local_user_${seed}`;
    const assistantLocalId = `local_assistant_${seed}`;
    currentUserLocalIdRef.current = userLocalId;
    currentAssistantLocalIdRef.current = assistantLocalId;
    setThreadError(null);
    setLocalMessages((previous) => [
      ...previous,
      {
        local_id: userLocalId,
        message_id: null,
        role: "user",
        content: question,
        citations: [],
        refusal: null,
        refusal_reason: null,
        suggestions: [],
        next_steps: [],
        timing: null,
        created_at: nowIsoString(),
        request_id: null,
        pending: false
      },
      {
        local_id: assistantLocalId,
        message_id: null,
        role: "assistant",
        content: "",
        citations: [],
        refusal: null,
        refusal_reason: null,
        suggestions: [],
        next_steps: [],
        timing: null,
        created_at: nowIsoString(),
        request_id: null,
        pending: true
      }
    ]);
    setComposerText("");
    setComposerStatus("sending");
    const controller = new AbortController();
    setStreamController(controller);
    let localRunId: string | null = null;
    let localConversationId = activeConversationId;
    const setConversation = (id: string) => {
      localConversationId = id;
      setActiveConversationId(id);
    };
    try {
      await askStreamByKb(
        finalKbId,
        {
          question,
          conversation_id: activeConversationId ?? undefined
        },
        {
          signal: controller.signal,
          onEvent: (event) => {
            if (event.event === "start") {
              localRunId = event.data.run_id;
            }
            applyStreamEvent(event, { userLocalId, assistantLocalId, setConversation });
          }
        }
      );
      setStreamController(null);
      setStreamRunId(null);
      setComposerStatus((current) => (current === "failed" ? current : "idle"));
      currentUserLocalIdRef.current = null;
      currentAssistantLocalIdRef.current = null;
      await refreshConversationList();
      if (localConversationId && hasAccessToken) {
        await loadMessages(localConversationId, false);
      }
    } catch (error) {
      if (isAbortError(error)) {
        setComposerStatus("idle");
      } else {
        const normalized = normalizeApiError(error);
        setThreadError(normalized);
        setComposerStatus("failed");
        message.error(formatApiErrorMessage(normalized));
      }
      patchLocalAssistant(assistantLocalId, (current) => ({
        pending: false,
        content: current.content || "生成已中断。"
      }));
      if (localRunId) {
        await recoverRun(localRunId);
      }
      setStreamController(null);
      setStreamRunId(null);
      currentUserLocalIdRef.current = null;
      currentAssistantLocalIdRef.current = null;
    }
  };

  const handleStop = async () => {
    if (!isBusy) {
      return;
    }
    setComposerStatus("stopping");
    if (streamRunId) {
      try {
        await cancelChatRun(streamRunId);
      } catch (error) {
        const normalized = normalizeApiError(error);
        setThreadError(normalized);
        message.error(formatApiErrorMessage(normalized));
        setComposerStatus("failed");
      }
      return;
    }
    streamController?.abort();
    const assistantLocalId = currentAssistantLocalIdRef.current;
    if (assistantLocalId) {
      patchLocalAssistant(assistantLocalId, (current) => ({
        pending: false,
        content: current.content || "生成已取消。"
      }));
    }
    setComposerStatus("idle");
  };

  const startNewChat = async () => {
    if (isBusy) {
      return;
    }
    setActiveAssistantKey(null);
    setActiveCitationId(null);
    setThreadError(null);
    setMessagesError(null);
    setLocalMessages([]);
    if (!hasAccessToken) {
      setActiveConversationId(null);
      setHistoryMessages([]);
      return;
    }
    const finalKbId = kbId.trim();
    if (!finalKbId) {
      message.warning("请选择知识库");
      return;
    }
    try {
      const created = await createConversationMutation.mutateAsync({
        kb_id: finalKbId,
        title: "新会话"
      });
      setActiveConversationId(created.conversation_id);
      setHistoryMessages([]);
      setMessagesHasMore(false);
      setMessagesBefore(null);
      await refreshConversationList();
    } catch (error) {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  };

  const openRenameDialog = () => {
    if (!activeConversationId) {
      return;
    }
    const current = conversationItems.find((item) => item.conversation_id === activeConversationId);
    setRenameTitle(current?.title ?? "");
    setRenameOpen(true);
  };

  const handleRename = async () => {
    if (!activeConversationId) {
      return;
    }
    setRenameLoading(true);
    try {
      await renameConversationMutation.mutateAsync({
        conversationId: activeConversationId,
        title: renameTitle.trim()
      });
      setRenameOpen(false);
      await refreshConversationList();
      message.success("会话名称已更新");
    } catch (error) {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    } finally {
      setRenameLoading(false);
    }
  };

  const handleDeleteConversation = () => {
    if (!activeConversationId) {
      return;
    }
    Modal.confirm({
      title: "删除当前会话",
      content: "删除后会话将从列表移除，是否继续？",
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await deleteConversationMutation.mutateAsync(activeConversationId);
          setActiveConversationId(null);
          setHistoryMessages([]);
          setLocalMessages([]);
          setActiveAssistantKey(null);
          setActiveCitationId(null);
          await refreshConversationList();
          message.success("会话已删除");
        } catch (error) {
          const normalized = normalizeApiError(error);
          message.error(formatApiErrorMessage(normalized));
        }
      }
    });
  };

  const handleFeedbackSubmit = async (
    messageId: string,
    payload: { rating: "up" | "down"; reasons: string[]; comment?: string; expected_hint?: string }
  ) => {
    setSubmittingFeedbackMessageId(messageId);
    try {
      await feedbackMutation.mutateAsync({ messageId, payload });
      setSubmittedFeedbackMap((previous) => ({ ...previous, [messageId]: true }));
      message.success("反馈已提交");
    } catch (error) {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
      throw error;
    } finally {
      setSubmittingFeedbackMessageId((current) => (current === messageId ? null : current));
    }
  };

  const handleRegenerate = async (messageId: string) => {
    setActioningMessageId(messageId);
    try {
      const result = await regenerateMutation.mutateAsync(messageId);
      if (result.conversation_id) {
        setActiveConversationId(result.conversation_id);
        await loadMessages(result.conversation_id, false);
      }
      await refreshConversationList();
      message.success("已重新生成回答");
    } catch (error) {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    } finally {
      setActioningMessageId(null);
    }
  };

  const findRelatedQuestion = (targetMessageId: string) => {
    const index = threadMessages.findIndex((item) => item.message_id === targetMessageId);
    if (index < 0) {
      return "";
    }
    const target = threadMessages[index];
    if (target.role === "user") {
      return target.content;
    }
    for (let i = index - 1; i >= 0; i -= 1) {
      if (threadMessages[i].role === "user") {
        return threadMessages[i].content;
      }
    }
    return "";
  };

  const openEditDialog = (messageId: string) => {
    setEditTargetMessageId(messageId);
    setEditQuestion(findRelatedQuestion(messageId));
    setEditOpen(true);
  };

  const openEvidenceModal = (assistant: ThreadMessage, citationId?: number) => {
    setActiveAssistantKey(messageKey(assistant));
    setActiveCitationId(citationId ?? null);
    setEvidenceOpen(true);
  };

  const handleApplyNextStep = (step: NextStepItem, citations: CitationItem[] = []) => {
    if (step.action === "check_official_source") {
      const sourceUrl = resolveOfficialSourceUrl(step, citations);
      if (sourceUrl) {
        window.open(sourceUrl, "_blank", "noopener,noreferrer");
        return;
      }
    }
    if (step.action === "check_official_source" || step.action === "verify_kb_scope") {
      if (role === "admin") {
        navigate(kbId ? `/admin/documents?kb=${encodeURIComponent(kbId)}` : "/admin/documents");
        return;
      }
      message.info("当前用户端无法直接打开文档管理页，请优先查看学校官网或联系管理员核对原文。");
      return;
    }
    const nextDraft = buildDraftFromNextStep(step, composerText);
    setComposerText(nextDraft);
  };

  const handleEditResend = async () => {
    if (!editTargetMessageId) {
      return;
    }
    const question = editQuestion.trim();
    if (!question) {
      message.warning("请输入编辑后的问题");
      return;
    }
    setActioningMessageId(editTargetMessageId);
    try {
      const result = await editResendMutation.mutateAsync({
        messageId: editTargetMessageId,
        question
      });
      if (result.conversation_id) {
        setActiveConversationId(result.conversation_id);
        await loadMessages(result.conversation_id, false);
      }
      setEditOpen(false);
      await refreshConversationList();
      message.success("已创建分支会话");
    } catch (error) {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    } finally {
      setActioningMessageId(null);
    }
  };

  const handleSignOut = async () => {
    if (!isAuthenticated || signingOut) {
      return;
    }
    setSigningOut(true);
    try {
      await signOut();
      message.success("已退出登录");
      navigate("/login?next=/app/ask");
    } catch (error) {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    } finally {
      setSigningOut(false);
    }
  };

  const sidebarStatus = !hasAccessToken
    ? "empty"
    : conversationQuery.isLoading
      ? "loading"
      : conversationQuery.isError
        ? "error"
        : conversationItems.length
          ? "success"
          : "empty";

  const threadStatus = messagesLoading
    ? "loading"
    : messagesError && !threadMessages.length
      ? "error"
      : threadMessages.length
        ? "success"
        : "empty";

  const kbOptions = (kbQuery.data?.items ?? []).map((item) => ({
    value: item.kb_id,
    label: item.name
  }));

  const selectedKbName = useMemo(() => {
    const items = kbQuery.data?.items ?? [];
    return items.find((item) => item.kb_id === kbId)?.name ?? null;
  }, [kbId, kbQuery.data?.items]);
  const kbCount = kbQuery.data?.items.length ?? 0;

  return (
    <div className="chat-shell">
      <Card className="chat-sidebar-card">
        <div className="chat-sidebar">
          <Tooltip
            placement="rightTop"
            title={
              <div className="chat-sidebar-brand-tooltip">
                <div className="chat-sidebar-brand-tooltip__title">
                  校园证据问答助手
                </div>
                <div className="chat-sidebar-brand-tooltip__desc">
                  基于证据的问答、引用与会话工作台
                </div>
              </div>
            }
          >
            <div className="brand-block chat-sidebar-brand">
              <div className="brand-lockup">
                <span className="brand-mark" aria-hidden="true">CS</span>
                <div className="brand-copy">
                  <Typography.Title level={4} className="brand-title">
                    CampusSage
                  </Typography.Title>
                  <Typography.Text className="brand-description">证据问答工作台</Typography.Text>
                </div>
              </div>
              <div className="chat-sidebar-brand__status">
                <span>引用优先</span>
                <span>拒答可追踪</span>
              </div>
              <div className="chat-sidebar-brand__overview">
                <div className="chat-sidebar-brand__overview-item">
                  <span className="chat-sidebar-brand__overview-label">知识库</span>
                  <span className="chat-sidebar-brand__overview-value">
                    {selectedKbName ?? `${kbCount} 个可选`}
                  </span>
                </div>
                <div className="chat-sidebar-brand__overview-item">
                  <span className="chat-sidebar-brand__overview-label">会话模式</span>
                  <span className="chat-sidebar-brand__overview-value">
                    {hasAccessToken ? "可追踪回放" : "游客即时问答"}
                  </span>
                </div>
                <div className="chat-sidebar-brand__overview-item">
                  <span className="chat-sidebar-brand__overview-label">当前上下文</span>
                  <span className="chat-sidebar-brand__overview-value">
                    {activeConversation ? "接续已有会话" : "准备新问题"}
                  </span>
                </div>
              </div>
            </div>
          </Tooltip>
          <div className="chat-sidebar-section-head">
            <Typography.Title level={5} className="chat-sidebar-section-title">
              你的聊天
            </Typography.Title>
            <span className="chat-sidebar-count">
              {hasAccessToken ? conversationItems.length : 0}
            </span>
          </div>

          <div className="chat-sidebar-controls">
            <div className="chat-sidebar-controls__head">
              <div className="chat-sidebar-controls__copy">
                <span className="chat-sidebar-controls__eyebrow">工作上下文</span>
                <Typography.Text strong>先选知识库，再继续会话</Typography.Text>
              </div>
              <Tag bordered={false} color={selectedKbName ? "geekblue" : "default"}>
                {selectedKbName ? "已绑定知识库" : "待选择"}
              </Tag>
            </div>
            <Select
              showSearch
              allowClear
              options={kbOptions}
              value={kbId || undefined}
              placeholder="选择知识库"
              onChange={(value) => {
                setKbId(typeof value === "string" ? value.trim() : "");
              }}
              optionFilterProp="label"
              filterOption={(inputValue, option) =>
                String(option?.label ?? "")
                  .toLowerCase()
                  .includes(inputValue.toLowerCase())
              }
            />
            <Input
              prefix={<SearchOutlined />}
              value={keyword}
              placeholder="搜索会话"
              allowClear
              onChange={(event) => {
                setKeyword(event.target.value);
              }}
            />
            <div className="chat-sidebar-toolbar">
              <Tooltip title="新建会话">
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  aria-label="新建会话"
                  onClick={() => void startNewChat()}
                  disabled={isBusy || !kbId}
                >
                  新建
                </Button>
              </Tooltip>
              <Tooltip title="重命名会话">
                <Button
                  icon={<EditOutlined />}
                  aria-label="重命名会话"
                  onClick={openRenameDialog}
                  disabled={!activeConversationId || isBusy}
                >
                  改名
                </Button>
              </Tooltip>
              <Tooltip title="删除会话">
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  aria-label="删除会话"
                  onClick={handleDeleteConversation}
                  disabled={!activeConversationId || isBusy}
                >
                  删除
                </Button>
              </Tooltip>
            </div>
          </div>

          <div className="chat-sidebar-list">
            {sidebarStatus === "loading" ? <Skeleton active paragraph={{ rows: 6 }} /> : null}
            {sidebarStatus === "empty" ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={hasAccessToken ? "暂无会话" : "登录后可查看会话列表"}
              />
            ) : null}
            {sidebarStatus === "error" ? (
              <RequestErrorAlert error={normalizeApiError(conversationQuery.error)} />
            ) : null}
            {sidebarStatus === "success"
              ? conversationItems.map((item) => (
                  <button
                    key={item.conversation_id}
                    type="button"
                    className={
                      activeConversationId === item.conversation_id
                        ? "chat-sidebar-item chat-sidebar-item--active"
                        : "chat-sidebar-item"
                    }
                    onClick={() => {
                      if (isBusy) {
                        return;
                      }
                      setActiveConversationId(item.conversation_id);
                      setLocalMessages([]);
                      setActiveAssistantKey(null);
                      setActiveCitationId(null);
                      setThreadError(null);
                    }}
                  >
                    <div className="chat-sidebar-item__head">
                      <span className="chat-sidebar-item__title">{item.title || "未命名会话"}</span>
                      <span className="chat-sidebar-item__badge">
                        {activeConversationId === item.conversation_id ? "当前" : "历史"}
                      </span>
                    </div>
                    <span className="chat-sidebar-item__preview">{summarizeConversation(item)}</span>
                    <div className="chat-sidebar-item__footer">
                      <span className="chat-sidebar-item__time">
                        {compactTime(item.last_message_at ?? item.updated_at)}
                      </span>
                      <span className="chat-sidebar-item__hint">
                        {activeConversationId === item.conversation_id ? "查看中" : "继续查看"}
                      </span>
                    </div>
                  </button>
                ))
              : null}
          </div>

          <div className="chat-sidebar-user">
            <div className="chat-sidebar-user__meta">
              <Typography.Text strong>
                {isAuthenticated ? user?.email ?? "当前用户" : "游客模式"}
              </Typography.Text>
              <Typography.Text type="secondary">点击回答查看引用。</Typography.Text>
            </div>
            {isAuthenticated ? (
              <div className="chat-sidebar-user__actions">
                {role === "admin" ? (
                  <PortalSwitch
                    activeRole="user"
                    onChange={(targetRole) => {
                      navigate(targetRole === "admin" ? "/admin/kb" : "/app/ask");
                    }}
                    compact
                    labelsHidden
                  />
                ) : null}
                <Tooltip title="退出登录">
                  <Button
                    size="small"
                    shape="circle"
                    icon={<LogoutOutlined />}
                    aria-label="退出登录"
                    onClick={() => void handleSignOut()}
                    loading={signingOut}
                  />
                </Tooltip>
              </div>
            ) : (
              <Tooltip title="登录">
                <Button
                  size="small"
                  shape="circle"
                  type="primary"
                  icon={<LoginOutlined />}
                  aria-label="登录"
                  onClick={() => {
                    navigate("/login?next=/app/ask");
                  }}
                />
              </Tooltip>
            )}
          </div>
        </div>
      </Card>

      <Card
        className="chat-thread-card"
        title={
          <div className="chat-thread-card-title">
            <Space size={8}>
              <MessageOutlined />
              <span>智能问答</span>
            </Space>
            <Typography.Text className="chat-thread-card-title__desc">
              基于知识库证据生成回答，证据不足时给出拒答建议。
            </Typography.Text>
          </div>
        }
      >
        <div className="chat-thread-head">
          <div className="chat-thread-intro">
            <div className="chat-thread-titlebar">
              <Space wrap>
                {selectedKbName ? <Tag color="geekblue">知识库：{selectedKbName}</Tag> : null}
                <Tag color={COMPOSER_STATUS_COLOR[composerStatus]} className="chat-status-tag">
                  状态：{COMPOSER_STATUS_LABEL[composerStatus]}
                </Tag>
              </Space>
              <Typography.Text className="chat-thread-kicker">
                点回答看引用
              </Typography.Text>
            </div>
            <Typography.Paragraph className="chat-thread-summary">
              {selectedKbName
                ? `当前围绕「${selectedKbName}」进行证据问答，回答会优先保留引用编号与定位信息。`
                : "先选择知识库，再发起问题；系统会优先返回带证据编号的答案与拒答建议。"}
            </Typography.Paragraph>
          </div>
          <div className="chat-thread-highlights" aria-label="问答能力">
            <span>证据引用</span>
            <span>拒答建议</span>
            <span>反馈回收</span>
          </div>
          <div className="chat-thread-kpis" aria-label="问答概览">
            <div className="chat-thread-kpi">
              <span className="chat-thread-kpi__label">会话状态</span>
              <span className="chat-thread-kpi__value">
                {activeConversation ? "已接续" : "新会话"}
              </span>
            </div>
            <div className="chat-thread-kpi">
              <span className="chat-thread-kpi__label">可用知识库</span>
              <span className="chat-thread-kpi__value">{kbCount}</span>
            </div>
            <div className="chat-thread-kpi">
              <span className="chat-thread-kpi__label">当前引用</span>
              <span className="chat-thread-kpi__value">{selectedAssistantCitationCount}</span>
            </div>
          </div>
        </div>

        {threadStatus === "success" && threadMessages.length ? (
          <div className="chat-insight-strip">
            <div className="chat-insight-strip__items">
              <div className="chat-insight-pill">
                <span className="chat-insight-pill__label">消息</span>
                <span className="chat-insight-pill__value">{threadMessages.length}</span>
              </div>
              <div className="chat-insight-pill">
                <span className="chat-insight-pill__label">回答 / 拒答</span>
                <span className="chat-insight-pill__value">
                  {answeredCount} / {refusedCount}
                </span>
              </div>
              <div className="chat-insight-pill">
                <span className="chat-insight-pill__label">证据覆盖</span>
                <span className="chat-insight-pill__value">{citationCoverage}%</span>
              </div>
              <div className="chat-insight-pill">
                <span className="chat-insight-pill__label">引用总数</span>
                <span className="chat-insight-pill__value">{totalCitationCount}</span>
              </div>
              {pendingCount ? (
                <div className="chat-insight-pill">
                  <span className="chat-insight-pill__label">生成中</span>
                  <span className="chat-insight-pill__value">{pendingCount}</span>
                </div>
              ) : null}
            </div>
            <div className="chat-insight-strip__coverage">
              <div className="chat-insight-strip__coverage-meta">
                <span>有引用回答 {citedAnswerCount}</span>
                <span>覆盖率 {citationCoverage}%</span>
              </div>
              <div className="chat-insight-strip__coverage-track" aria-hidden="true">
                <div
                  className="chat-insight-strip__coverage-fill"
                  style={{ width: `${citationCoverage}%` }}
                />
              </div>
            </div>
          </div>
        ) : null}

        {threadError ? <RequestErrorAlert error={threadError} /> : null}
        {messagesError ? <RequestErrorAlert error={messagesError} /> : null}

        <div ref={threadViewportRef} className="chat-thread-viewport">
          {messagesHasMore && threadStatus === "success" ? (
            <div className="chat-thread-loadmore">
              <Button
                icon={<HistoryOutlined />}
                loading={messagesLoading}
                onClick={() => {
                  if (activeConversationId) {
                    void loadMessages(activeConversationId, true);
                  }
                }}
              >
                加载更早消息
              </Button>
            </div>
          ) : null}

          {threadStatus === "loading" ? <Skeleton active paragraph={{ rows: 7 }} /> : null}
          {threadStatus === "error" ? <Alert type="error" showIcon message="消息加载失败" /> : null}
          {threadStatus === "empty" ? (
            <div className="chat-empty-panel">
              <div className="chat-empty-panel__main">
                <div className="chat-empty-panel__eyebrow">Ask With Evidence</div>
                <div className="chat-empty-panel__mark" aria-hidden="true">
                  <MessageOutlined />
                </div>
                <Typography.Title level={3} className="chat-empty-panel__title">
                  {activeConversationId ? "当前会话暂无消息" : "开始一次有证据的校园问答"}
                </Typography.Title>
                <Typography.Paragraph className="chat-empty-panel__desc">
                  选择知识库后输入问题，回答会保留引用编号；证据不足时会给出下一步建议。
                </Typography.Paragraph>
                <Typography.Text className="chat-empty-panel__prompt-label">
                  可以先从这些常见问题开始
                </Typography.Text>
                <div className="chat-empty-panel__prompts">
                  {QUESTION_STARTERS.map((question) => (
                    <button
                      key={question}
                      type="button"
                      className="chat-empty-prompt"
                      onClick={() => {
                        setComposerText(question);
                      }}
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>
              <div className="chat-empty-panel__assurance" aria-label="证据问答约束">
                <div className="chat-empty-panel__assurance-head">
                  <span className="chat-empty-panel__assurance-title">可信回答约束</span>
                  <span className="chat-empty-panel__assurance-state">
                    {selectedKbName ? "已绑定知识库" : "待选择知识库"}
                  </span>
                </div>
                {QUALITY_PROMISES.map((item) => (
                  <div key={item.label} className="chat-empty-assurance-item">
                    <span className="chat-empty-assurance-item__label">{item.label}</span>
                    <span className="chat-empty-assurance-item__value">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {threadStatus === "success"
            ? threadMessages.map((item) => (
                <div
                  key={item.local_id}
                  className={
                    item.role === "user"
                      ? "chat-message-row chat-message-row--user"
                      : "chat-message-row chat-message-row--assistant"
                  }
                >
                  <article
                    className={
                      item.role === "user"
                        ? "chat-bubble chat-bubble--user"
                        : "chat-bubble chat-bubble--assistant"
                    }
                    onClick={(event) => {
                      if (item.role === "assistant") {
                        const target = event.target as HTMLElement;
                        if (target.closest(".chat-bubble-actions")) {
                          return;
                        }
                        openEvidenceModal(item);
                      }
                    }}
                  >
                    <header className="chat-bubble__header">
                      <Space size={8}>
                        <Tag color={item.role === "user" ? "blue" : "green"}>
                          {item.role === "user" ? "用户" : "助手"}
                        </Tag>
                        {item.pending ? <Tag color="processing">生成中</Tag> : null}
                        {item.refusal ? <Tag color="warning">拒答</Tag> : null}
                      </Space>
                      <Typography.Text type="secondary">{compactTime(item.created_at)}</Typography.Text>
                    </header>
                    <div className="chat-bubble__meta">
                      {item.role === "assistant" ? (
                        <>
                          <span>
                            {item.citations.length
                              ? `引用 ${item.citations.length} 条`
                              : item.refusal
                                ? "证据不足已拒答"
                                : "等待引用写回"}
                          </span>
                          <span>{item.refusal ? "已生成下一步建议" : "点击消息查看证据面板"}</span>
                        </>
                      ) : (
                        <span>{selectedKbName ? `已提交到 ${selectedKbName}` : "问题已提交"}</span>
                      )}
                    </div>
                    <Typography.Paragraph className="chat-bubble__content">
                      {item.role === "assistant"
                        ? renderWithMarkers(item.content, (citationId) => {
                            openEvidenceModal(item, citationId);
                          })
                        : item.content}
                    </Typography.Paragraph>
                    {item.refusal ? (
                      <RefusalNextStepsCard
                        nextSteps={item.next_steps}
                        suggestions={item.suggestions}
                        onApplyStep={(step) => {
                          handleApplyNextStep(step, item.citations);
                        }}
                      />
                    ) : null}
                    {item.role === "assistant" ? (
                      <Space wrap className="chat-bubble-actions">
                        {item.message_id ? (
                          <FeedbackAction
                            messageId={item.message_id}
                            submitting={submittingFeedbackMessageId === item.message_id}
                            submitted={Boolean(submittedFeedbackMap[item.message_id])}
                            onSubmit={handleFeedbackSubmit}
                          />
                        ) : null}
                        {item.message_id ? (
                          <Tooltip title="重试">
                            <Button
                              size="small"
                              shape="circle"
                              icon={<HistoryOutlined />}
                              aria-label="重试"
                              loading={actioningMessageId === item.message_id && regenerateMutation.isPending}
                              onClick={() => {
                                void handleRegenerate(item.message_id as string);
                              }}
                            />
                          </Tooltip>
                        ) : null}
                        {item.message_id ? (
                          <Tooltip title="改写后重发">
                            <Button
                              size="small"
                              shape="circle"
                              icon={<EditOutlined />}
                              aria-label="改写后重发"
                              loading={actioningMessageId === item.message_id && editResendMutation.isPending}
                              onClick={() => {
                                openEditDialog(item.message_id as string);
                              }}
                            />
                          </Tooltip>
                        ) : null}
                      </Space>
                    ) : null}
                  </article>
                </div>
              ))
            : null}
        </div>

        <div className="chat-composer-shell">
          <div className="chat-composer">
            <div className="chat-composer__header">
              <div className="chat-composer__copy">
                <span className="chat-composer__eyebrow">提问区</span>
                <Typography.Text strong>围绕单一事务提问，答案会保留引用编号。</Typography.Text>
              </div>
              <Tag bordered={false} color={selectedKbName ? "geekblue" : "default"}>
                {selectedKbName ? "已选知识库" : "请先选择知识库"}
              </Tag>
            </div>
            <Input.TextArea
              value={composerText}
              autoSize={{ minRows: 3, maxRows: 8 }}
              placeholder="请输入你的问题，Enter 发送，Shift + Enter 换行"
              onChange={(event) => {
                setComposerText(event.target.value);
              }}
              onPressEnter={(event) => {
                if (event.shiftKey) {
                  return;
                }
                event.preventDefault();
                if (isBusy) {
                  return;
                }
                void handleSend();
              }}
            />
            <div className="chat-composer-quick-actions" aria-label="示例问题快捷填充">
              {COMPOSER_SHORTCUTS.map((shortcut) => (
                <button
                  key={shortcut.label}
                  type="button"
                  className="chat-composer-quick-action"
                  onClick={() => {
                    setComposerText(shortcut.value);
                  }}
                >
                  {shortcut.label}
                </button>
              ))}
            </div>
            <div className="chat-composer-actions">
              <div className="chat-composer-meta">
                <Typography.Text type="secondary">引用编号会保留在回答里。</Typography.Text>
                {selectedKbName ? (
                  <span className="chat-composer-meta__kb">{selectedKbName}</span>
                ) : null}
              </div>
              <Space>
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={() => {
                    void handleSend();
                  }}
                  loading={composerStatus === "sending" || composerStatus === "streaming"}
                  disabled={isBusy || !composerText.trim() || !kbId}
                >
                  发送
                </Button>
                <Button danger icon={<StopOutlined />} onClick={() => void handleStop()} disabled={!isBusy}>
                  停止
                </Button>
              </Space>
            </div>
          </div>
        </div>
      </Card>

      <Modal
        title="证据面板"
        open={evidenceOpen}
        onCancel={() => {
          setEvidenceOpen(false);
        }}
        footer={null}
        width={760}
        destroyOnHidden
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Typography.Text type="secondary">按键或点右上角关闭</Typography.Text>
          {!selectedAssistant ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一条助手消息查看证据与耗时" />
          ) : (
            <>
              <Tag color={selectedAssistant.refusal ? "warning" : "success"}>
                {selectedAssistant.refusal ? "拒答结果" : "回答结果"}
              </Tag>
              {selectedAssistant.refusal_reason ? (
                <Alert type="warning" showIcon message={selectedAssistant.refusal_reason} />
              ) : null}
              {selectedAssistant.refusal ? (
                <RefusalNextStepsCard
                  nextSteps={selectedAssistant.next_steps}
                  suggestions={selectedAssistant.suggestions}
                  onApplyStep={(step) => {
                    handleApplyNextStep(step, selectedAssistant.citations);
                  }}
                />
              ) : null}
              {selectedAssistant.timing ? (
                <Card size="small" title="耗时信息">
                  <Space wrap>
                    {Object.entries(selectedAssistant.timing).map(([field, value]) => (
                      <Tag key={field}>
                        {field}: {value}ms
                      </Tag>
                    ))}
                  </Space>
                </Card>
              ) : null}
              <Card size="small" title={`引用 (${selectedAssistant.citations.length})`}>
                {selectedAssistant.citations.length === 0 ? (
                  <Typography.Text type="secondary">当前消息暂无引用。</Typography.Text>
                ) : (
                  <Space direction="vertical" size={10} style={{ width: "100%" }}>
                    {selectedAssistant.citations.map((citation) => {
                      const refKey = `${messageKey(selectedAssistant)}_${citation.citation_id}`;
                      return (
                        <Card
                          key={`${citation.chunk_id}_${citation.citation_id}`}
                          size="small"
                          className={
                            citation.citation_id === activeCitationId
                              ? "citation-card citation-card--active"
                              : "citation-card"
                          }
                        >
                          <div
                            ref={(node) => {
                              citationRefs.current[refKey] = node;
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
                      );
                    })}
                  </Space>
                )}
              </Card>
            </>
          )}
        </Space>
      </Modal>

      <Modal
        title="重命名会话"
        open={renameOpen}
        okText="保存"
        cancelText="取消"
        confirmLoading={renameLoading}
        onOk={() => {
          void handleRename();
        }}
        onCancel={() => {
          if (renameLoading) {
            return;
          }
          setRenameOpen(false);
        }}
      >
        <Input
          value={renameTitle}
          placeholder="请输入会话名称"
          onChange={(event) => {
            setRenameTitle(event.target.value);
          }}
          maxLength={80}
        />
      </Modal>

      <Modal
        title="编辑后重发"
        open={editOpen}
        okText="发送"
        cancelText="取消"
        confirmLoading={editResendMutation.isPending}
        onOk={() => {
          void handleEditResend();
        }}
        onCancel={() => {
          if (editResendMutation.isPending) {
            return;
          }
          setEditOpen(false);
        }}
      >
        <Input.TextArea
          value={editQuestion}
          autoSize={{ minRows: 4, maxRows: 8 }}
          placeholder="请输入编辑后的问题"
          onChange={(event) => {
            setEditQuestion(event.target.value);
          }}
        />
      </Modal>
    </div>
  );
}
