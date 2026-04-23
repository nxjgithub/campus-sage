import { apiClient } from "../client";
import { CitationItem, NextStepItem } from "./ask";

export interface ConversationListItem {
  conversation_id: string;
  kb_id: string;
  title?: string | null;
  last_message_preview?: string | null;
  last_message_at?: string | null;
  updated_at: string;
}

export interface ConversationListResponse {
  items: ConversationListItem[];
  total: number;
  next_cursor?: string | null;
  request_id?: string | null;
}

export interface ConversationMessage {
  message_id: string;
  parent_message_id?: string | null;
  edited_from_message_id?: string | null;
  role: "user" | "assistant";
  content: string;
  citations?: CitationItem[] | null;
  refusal?: boolean | null;
  refusal_reason?: string | null;
  suggestions?: string[] | null;
  next_steps?: NextStepItem[] | null;
  timing?: Record<string, number> | null;
  created_at: string;
  request_id?: string | null;
}

export interface ConversationDetailResponse {
  conversation_id: string;
  kb_id: string;
  messages: ConversationMessage[];
  request_id?: string | null;
}

export interface MessagePageResponse {
  items: ConversationMessage[];
  has_more: boolean;
  next_before?: string | null;
  request_id?: string | null;
}

export interface FeedbackPayload {
  rating: "up" | "down";
  reasons: string[];
  comment?: string;
  expected_hint?: string;
}

export interface ConversationCreatePayload {
  kb_id: string;
  title?: string;
}

export interface ConversationCreateResponse {
  conversation_id: string;
  kb_id: string;
  title?: string | null;
  created_at: string;
  updated_at: string;
  request_id?: string | null;
}

export interface ConversationRenamePayload {
  title?: string;
}

export interface ConversationListParams {
  kb_id?: string;
  keyword?: string;
  cursor?: string;
  limit?: number;
  offset?: number;
}

export interface ConversationMessagePageParams {
  before?: string;
  limit?: number;
}

export async function fetchConversationList(params?: {
  kb_id?: string;
  keyword?: string;
  cursor?: string;
  limit?: number;
  offset?: number;
}) {
  const { data } = await apiClient.get<ConversationListResponse>("/conversations", {
    params
  });
  return data;
}

export async function fetchConversationDetail(conversationId: string) {
  const { data } = await apiClient.get<ConversationDetailResponse>(
    `/conversations/${conversationId}`
  );
  return data;
}

export async function fetchConversationMessagesPage(
  conversationId: string,
  params?: ConversationMessagePageParams
) {
  const { data } = await apiClient.get<MessagePageResponse>(
    `/conversations/${conversationId}/messages`,
    { params }
  );
  return data;
}

export async function createConversation(payload: ConversationCreatePayload) {
  const { data } = await apiClient.post<ConversationCreateResponse>("/conversations", payload);
  return data;
}

export async function renameConversation(
  conversationId: string,
  payload: ConversationRenamePayload
) {
  const { data } = await apiClient.patch<ConversationCreateResponse>(
    `/conversations/${conversationId}`,
    payload
  );
  return data;
}

export async function deleteConversation(conversationId: string) {
  const { data } = await apiClient.delete<{
    conversation_id: string;
    status: "deleted";
    request_id?: string | null;
  }>(`/conversations/${conversationId}`);
  return data;
}

export async function submitFeedback(messageId: string, payload: FeedbackPayload) {
  const { data } = await apiClient.post<{
    feedback_id: string;
    message_id: string;
    status: string;
    request_id?: string | null;
  }>(`/messages/${messageId}/feedback`, payload);
  return data;
}
