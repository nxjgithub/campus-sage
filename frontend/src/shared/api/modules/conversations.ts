import { apiClient } from "../client";

export interface ConversationListItem {
  conversation_id: string;
  kb_id: string;
  title?: string | null;
  updated_at: string;
}

export interface ConversationListResponse {
  items: ConversationListItem[];
  request_id?: string | null;
}

export interface ConversationMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Array<Record<string, unknown>> | null;
  refusal?: boolean | null;
  refusal_reason?: string | null;
  timing?: Record<string, number> | null;
  created_at: string;
}

export interface ConversationDetailResponse {
  conversation_id: string;
  kb_id: string;
  messages: ConversationMessage[];
  request_id?: string | null;
}

export interface FeedbackPayload {
  rating: "up" | "down";
  reasons: string[];
  comment?: string;
  expected_hint?: string;
}

export async function fetchConversationList(params?: {
  kb_id?: string;
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

export async function submitFeedback(messageId: string, payload: FeedbackPayload) {
  const { data } = await apiClient.post<{
    feedback_id: string;
    message_id: string;
    status: string;
    request_id?: string | null;
  }>(`/messages/${messageId}/feedback`, payload);
  return data;
}
