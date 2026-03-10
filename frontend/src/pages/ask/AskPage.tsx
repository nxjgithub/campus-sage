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

  return (
    <div className="chat-shell">
      <Card className="chat-sidebar-card">
        <div className="chat-sidebar">
          <Tooltip
            placement="rightTop"
            title={
              <div className="chat-sidebar-brand-tooltip">
                <div className="chat-sidebar-brand-tooltip__title">
                  Evidence-grounded University Knowledge Assistant
                </div>
                <div className="chat-sidebar-brand-tooltip__desc">
                  RAG 检索增强问答平台 · 会话、引用、评测、监控一体化
                </div>
              </div>
            }
          >
            <div className="brand-block chat-sidebar-brand">
              <Typography.Title level={4} className="brand-title">
                CampusSage
              </Typography.Title>
              <Typography.Text className="brand-subtitle">用户端</Typography.Text>
            </div>
          </Tooltip>
          <Typography.Title level={5} className="chat-sidebar-section-title">
            你的聊天
          </Typography.Title>

          <div className="chat-sidebar-controls">
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
              <Button type="primary" icon={<PlusOutlined />} onClick={() => void startNewChat()} disabled={isBusy || !kbId}>
                新建
              </Button>
              <Button icon={<EditOutlined />} onClick={openRenameDialog} disabled={!activeConversationId || isBusy}>
                重命名
              </Button>
              <Button danger icon={<DeleteOutlined />} onClick={handleDeleteConversation} disabled={!activeConversationId || isBusy}>
                删除
              </Button>
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
                    <span className="chat-sidebar-item__title">{item.title || "未命名会话"}</span>
                    <span className="chat-sidebar-item__preview">{summarizeConversation(item)}</span>
                    <span className="chat-sidebar-item__time">
                      {compactTime(item.last_message_at ?? item.updated_at)}
                    </span>
                  </button>
                ))
              : null}
          </div>

          <div className="chat-sidebar-user">
            <div className="chat-sidebar-user__meta">
              <Typography.Text strong>
                {isAuthenticated ? user?.email ?? "当前用户" : "游客模式"}
              </Typography.Text>
              <Typography.Text type="secondary">基于证据回答，点击助手消息可查看引用与耗时。</Typography.Text>
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
                  />
                ) : null}
                <Button size="small" icon={<LogoutOutlined />} onClick={() => void handleSignOut()} loading={signingOut}>
                  退出
                </Button>
              </div>
            ) : (
              <Button
                size="small"
                type="primary"
                icon={<LoginOutlined />}
                onClick={() => {
                  navigate("/login?next=/app/ask");
                }}
              >
                登录
              </Button>
            )}
          </div>
        </div>
      </Card>

      <Card className="chat-thread-card" title={<Space size={8}><MessageOutlined /><span>智能问答</span></Space>}>
        <div className="chat-thread-head">
          <Space wrap>
            {selectedKbName ? <Tag color="geekblue">知识库：{selectedKbName}</Tag> : null}
            <Tag color={COMPOSER_STATUS_COLOR[composerStatus]} className="chat-status-tag">状态：{COMPOSER_STATUS_LABEL[composerStatus]}</Tag>
          </Space>
        </div>

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
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={activeConversationId ? "当前会话暂无消息" : "开始提问，生成第一条消息"}
            />
          ) : null}

          {threadStatus === "success"
            ? threadMessages.map((item) => (
                <article
                  key={item.local_id}
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
                  <Typography.Paragraph className="chat-bubble__content">
                    {item.role === "assistant"
                      ? renderWithMarkers(item.content, (citationId) => {
                          openEvidenceModal(item, citationId);
                        })
                      : item.content}
                  </Typography.Paragraph>
                  {item.refusal && item.suggestions.length ? (
                    <Card size="small" title="下一步建议" className="chat-refusal-card">
                      <ul className="muted-list">
                        {item.suggestions.map((tip) => (
                          <li key={tip}>{tip}</li>
                        ))}
                      </ul>
                    </Card>
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
                        <Button
                          size="small"
                          icon={<HistoryOutlined />}
                          loading={actioningMessageId === item.message_id && regenerateMutation.isPending}
                          onClick={() => {
                            void handleRegenerate(item.message_id as string);
                          }}
                        >
                          重试
                        </Button>
                      ) : null}
                      {item.message_id ? (
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          loading={actioningMessageId === item.message_id && editResendMutation.isPending}
                          onClick={() => {
                            openEditDialog(item.message_id as string);
                          }}
                        >
                          改写
                        </Button>
                      ) : null}
                    </Space>
                  ) : null}
                </article>
              ))
            : null}
        </div>

        <div className="chat-composer-shell">
          <div className="chat-composer">
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
            <div className="chat-composer-actions">
              <Typography.Text type="secondary">回答会自动保留引用编号，可随时打开证据面板查看来源。</Typography.Text>
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
          <Typography.Text type="secondary">按任意键或点击右上角关闭</Typography.Text>
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
