import { apiClient } from "../client";
import { ApiErrorShape } from "../errors";
import { getAccessToken } from "../../auth/token";

export interface AskFilters {
  doc_ids?: string[];
  published_after?: string;
}

export interface AskRuntimeConfig {
  topk?: number;
  threshold?: number;
  rerank_enabled?: boolean;
  filters?: AskFilters;
  debug?: boolean;
}

export interface AskRequest extends AskRuntimeConfig {
  question: string;
  conversation_id?: string;
}

export interface CitationItem {
  citation_id: number;
  doc_id: string;
  doc_name: string;
  doc_version?: string | null;
  published_at?: string | null;
  page_start?: number | null;
  page_end?: number | null;
  section_path?: string | null;
  chunk_id: string;
  snippet: string;
  score?: number | null;
}

export interface AskResponse {
  answer: string;
  refusal: boolean;
  refusal_reason?: string | null;
  suggestions: string[];
  citations: CitationItem[];
  conversation_id?: string | null;
  message_id?: string | null;
  user_message_id?: string | null;
  assistant_created_at?: string | null;
  timing?: Record<string, number> | null;
  request_id?: string | null;
}

export interface ChatRunResponse {
  run_id: string;
  kb_id?: string | null;
  conversation_id?: string | null;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
  status: "running" | "succeeded" | "failed" | "canceled";
  cancel_flag: boolean;
  started_at: string;
  finished_at?: string | null;
  request_id?: string | null;
}

export interface ChatRunCancelResponse {
  run_id: string;
  status: "running" | "succeeded" | "failed" | "canceled";
  cancel_flag: boolean;
  request_id?: string | null;
}

export interface RegenerateRequest extends AskRuntimeConfig {}

export interface EditAndResendRequest extends AskRuntimeConfig {
  question: string;
}

export interface AskStreamStartData {
  run_id: string;
  conversation_id?: string | null;
  request_id?: string | null;
}

export interface AskStreamPingData {
  run_id: string;
  request_id?: string | null;
}

export interface AskStreamTokenData {
  run_id: string;
  delta: string;
  request_id?: string | null;
}

export interface AskStreamCitationData {
  run_id: string;
  citation: CitationItem;
  request_id?: string | null;
}

export interface AskStreamRefusalData {
  run_id: string;
  answer: string;
  refusal_reason?: string | null;
  suggestions: string[];
  conversation_id?: string | null;
  user_message_id?: string | null;
  message_id?: string | null;
  assistant_created_at?: string | null;
  timing?: Record<string, number> | null;
  request_id?: string | null;
}

export interface AskStreamDoneData {
  run_id: string;
  status: "succeeded" | "failed" | "canceled";
  conversation_id?: string | null;
  user_message_id?: string | null;
  message_id?: string | null;
  assistant_created_at?: string | null;
  refusal?: boolean | null;
  timing?: Record<string, number> | null;
  request_id?: string | null;
}

export interface AskStreamErrorData {
  run_id: string;
  code: string;
  message: string;
  detail?: unknown;
  user_message_id?: string | null;
  request_id?: string | null;
}

export type AskStreamEvent =
  | { event: "start"; data: AskStreamStartData }
  | { event: "ping"; data: AskStreamPingData }
  | { event: "token"; data: AskStreamTokenData }
  | { event: "citation"; data: AskStreamCitationData }
  | { event: "refusal"; data: AskStreamRefusalData }
  | { event: "done"; data: AskStreamDoneData }
  | { event: "error"; data: AskStreamErrorData };

export interface AskStreamOptions {
  signal?: AbortSignal;
  onEvent?: (event: AskStreamEvent) => void;
}

export async function askByKb(kbId: string, payload: AskRequest) {
  const { data } = await apiClient.post<AskResponse>(`/kb/${kbId}/ask`, payload);
  return data;
}

export async function regenerateMessage(messageId: string, payload: RegenerateRequest = {}) {
  const { data } = await apiClient.post<AskResponse>(`/messages/${messageId}/regenerate`, payload);
  return data;
}

export async function editAndResendMessage(messageId: string, payload: EditAndResendRequest) {
  const { data } = await apiClient.post<AskResponse>(
    `/messages/${messageId}/edit-and-resend`,
    payload
  );
  return data;
}

export async function getChatRun(runId: string) {
  const { data } = await apiClient.get<ChatRunResponse>(`/chat/runs/${runId}`);
  return data;
}

export async function cancelChatRun(runId: string) {
  const { data } = await apiClient.post<ChatRunCancelResponse>(`/chat/runs/${runId}/cancel`);
  return data;
}

function buildStreamHeaders(requestId: string) {
  const headers = new Headers();
  headers.set("Accept", "text/event-stream");
  headers.set("Content-Type", "application/json");
  headers.set("X-Request-ID", requestId);
  const accessToken = getAccessToken();
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return headers;
}

function nextRequestId() {
  return `req_${crypto.randomUUID().replace(/-/g, "")}`;
}

function resolveApiBaseUrl() {
  const value = apiClient.defaults.baseURL;
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return "/api/v1";
}

function resolveApiErrorFromResponse(
  response: Response,
  payload: {
    error?: { code?: string; message?: string; detail?: unknown };
    request_id?: string | null;
  } | null
): ApiErrorShape {
  return {
    code: payload?.error?.code ?? `HTTP_${response.status}`,
    message: payload?.error?.message ?? `请求失败（${response.status}）`,
    detail: payload?.error?.detail,
    request_id: payload?.request_id ?? response.headers.get("X-Request-ID")
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return value as Record<string, unknown>;
}

function toStreamEvent(name: string, rawData: unknown): AskStreamEvent {
  const data = asRecord(rawData);
  if (name === "start") {
    return { event: "start", data: data as unknown as AskStreamStartData };
  }
  if (name === "ping") {
    return { event: "ping", data: data as unknown as AskStreamPingData };
  }
  if (name === "token") {
    return { event: "token", data: data as unknown as AskStreamTokenData };
  }
  if (name === "citation") {
    return { event: "citation", data: data as unknown as AskStreamCitationData };
  }
  if (name === "refusal") {
    return { event: "refusal", data: data as unknown as AskStreamRefusalData };
  }
  if (name === "done") {
    return { event: "done", data: data as unknown as AskStreamDoneData };
  }
  return { event: "error", data: data as unknown as AskStreamErrorData };
}

function consumeSseLine(
  line: string,
  state: { eventName: string; dataLines: string[]; onEvent?: (event: AskStreamEvent) => void }
) {
  if (!line) {
    if (!state.dataLines.length) {
      return;
    }
    const payload = state.dataLines.join("\n");
    let parsed: unknown = payload;
    try {
      parsed = JSON.parse(payload);
    } catch {
      parsed = { message: payload };
    }
    state.onEvent?.(toStreamEvent(state.eventName, parsed));
    state.eventName = "message";
    state.dataLines = [];
    return;
  }
  if (line.startsWith("event:")) {
    state.eventName = line.slice(6).trim();
    return;
  }
  if (line.startsWith("data:")) {
    state.dataLines.push(line.slice(5).trimStart());
  }
}

export async function askStreamByKb(
  kbId: string,
  payload: AskRequest,
  options: AskStreamOptions = {}
) {
  const requestId = nextRequestId();
  const response = await fetch(`${resolveApiBaseUrl()}/kb/${encodeURIComponent(kbId)}/ask/stream`, {
    method: "POST",
    headers: buildStreamHeaders(requestId),
    body: JSON.stringify(payload),
    signal: options.signal
  });

  if (!response.ok) {
    let payloadData: {
      error?: { code?: string; message?: string; detail?: unknown };
      request_id?: string | null;
    } | null = null;
    try {
      payloadData = (await response.json()) as {
        error?: { code?: string; message?: string; detail?: unknown };
        request_id?: string | null;
      };
    } catch {
      payloadData = null;
    }
    throw resolveApiErrorFromResponse(response, payloadData);
  }

  if (!response.body) {
    throw {
      code: "STREAM_NO_BODY",
      message: "流式响应体为空",
      request_id: response.headers.get("X-Request-ID")
    } as ApiErrorShape;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  const parserState = {
    eventName: "message",
    dataLines: [] as string[],
    onEvent: options.onEvent
  };
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let lineBreakIndex = buffer.indexOf("\n");
    while (lineBreakIndex >= 0) {
      const rawLine = buffer.slice(0, lineBreakIndex);
      const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
      consumeSseLine(line, parserState);
      buffer = buffer.slice(lineBreakIndex + 1);
      lineBreakIndex = buffer.indexOf("\n");
    }
  }

  if (buffer.trim()) {
    const lines = buffer.split(/\r?\n/);
    for (const line of lines) {
      consumeSseLine(line, parserState);
    }
  }
  consumeSseLine("", parserState);
}
