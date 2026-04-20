import axios, { AxiosError } from "axios";

export interface ApiErrorShape {
  code: string;
  message: string;
  detail?: unknown;
  request_id?: string | null;
}

export interface ApiErrorDisplay {
  summary: string;
  nextStep?: string;
}

const API_ERROR_DISPLAY_MAP: Record<string, ApiErrorDisplay> = {
  NETWORK_ERROR: {
    summary: "网络连接失败，请检查当前网络后重试。",
    nextStep: "如果后端服务刚启动完成，等待几秒后再次尝试。"
  },
  UNKNOWN_ERROR: {
    summary: "处理请求时出现未知异常，请稍后重试。"
  },
  VALIDATION_FAILED: {
    summary: "提交的信息不完整或格式不正确，请检查后重试。",
    nextStep: "请根据表单提示修正输入项。"
  },
  KB_NOT_FOUND: {
    summary: "目标知识库不存在或已被删除。",
    nextStep: "请刷新列表后重新选择知识库。"
  },
  KB_ALREADY_EXISTS: {
    summary: "知识库名称已存在，请更换名称后重试。"
  },
  DOCUMENT_NOT_FOUND: {
    summary: "目标文档不存在或已被删除。",
    nextStep: "请刷新文档列表后重试。"
  },
  INGEST_JOB_NOT_FOUND: {
    summary: "入库任务不存在或已失效。",
    nextStep: "请刷新任务列表后重试。"
  },
  INGEST_JOB_NOT_RETRYABLE: {
    summary: "当前任务状态不允许重试。",
    nextStep: "请先查看任务状态，必要时重新发起入库。"
  },
  CONVERSATION_NOT_FOUND: {
    summary: "目标会话不存在或已被删除。",
    nextStep: "请刷新会话列表后重新进入。"
  },
  MESSAGE_NOT_FOUND: {
    summary: "目标消息不存在或已被删除。",
    nextStep: "请刷新当前会话后重试。"
  },
  CHAT_RUN_NOT_FOUND: {
    summary: "生成任务不存在或已结束。",
    nextStep: "请重新发起一次问答。"
  },
  CHAT_RUN_CANCELED: {
    summary: "本次生成已取消。"
  },
  FILE_TYPE_NOT_ALLOWED: {
    summary: "当前文件类型不受支持。",
    nextStep: "请改用 PDF、DOCX、HTML、Markdown 或 TXT 文件。"
  },
  FILE_TOO_LARGE: {
    summary: "上传文件大小超过限制。",
    nextStep: "请压缩文件或拆分后重新上传。"
  },
  AUTH_INVALID_CREDENTIALS: {
    summary: "邮箱或密码不正确，请重新输入。"
  },
  AUTH_UNAUTHORIZED: {
    summary: "当前登录状态已失效，请重新登录。"
  },
  AUTH_FORBIDDEN: {
    summary: "当前账号没有执行该操作的权限。"
  },
  AUTH_TOKEN_EXPIRED: {
    summary: "登录已过期，请重新登录后继续操作。"
  },
  AUTH_TOKEN_INVALID: {
    summary: "登录凭证无效，请重新登录。"
  },
  INGEST_PARSE_FAILED: {
    summary: "文档解析失败，暂时无法完成入库。",
    nextStep: "请检查文档是否损坏，或改用其他格式后重试。"
  },
  INGEST_CHUNK_FAILED: {
    summary: "文档切分失败，暂时无法完成入库。"
  },
  INGEST_EMBED_FAILED: {
    summary: "向量化处理失败，暂时无法完成入库。",
    nextStep: "请稍后重试；若持续失败，请检查嵌入服务状态。"
  },
  INGEST_CANCELED: {
    summary: "入库任务已取消。"
  },
  INGEST_QUEUE_UNAVAILABLE: {
    summary: "入库队列当前不可用。",
    nextStep: "请稍后重试，或联系管理员检查队列服务。"
  },
  INGEST_WORKER_FAILED: {
    summary: "入库任务执行失败。",
    nextStep: "请稍后重试，或联系管理员检查 Worker 状态。"
  },
  EMBEDDING_FAILED: {
    summary: "嵌入服务暂时不可用。",
    nextStep: "请稍后重试。"
  },
  VECTOR_UPSERT_FAILED: {
    summary: "向量写入失败，当前无法完成入库。",
    nextStep: "请稍后重试，或联系管理员检查向量库状态。"
  },
  VECTOR_SEARCH_FAILED: {
    summary: "检索服务暂时不可用。",
    nextStep: "请稍后重试。"
  },
  RAG_CONTEXT_BUILD_FAILED: {
    summary: "构建回答上下文时出现异常。",
    nextStep: "请尝试缩短问题或补充更明确的描述。"
  },
  RAG_MODEL_FAILED: {
    summary: "生成服务暂时不可用。",
    nextStep: "请保留当前问题，稍后再次尝试。"
  },
  RAG_NO_EVIDENCE: {
    summary: "当前知识库中的证据不足，暂时无法回答该问题。",
    nextStep: "请换一种问法，或补充更多上下文后重试。"
  },
  RAG_PAYLOAD_INVALID: {
    summary: "检索数据格式异常，当前无法完成回答。"
  },
  USER_NOT_FOUND: {
    summary: "目标用户不存在或已被删除。",
    nextStep: "请刷新用户列表后重试。"
  },
  USER_ALREADY_EXISTS: {
    summary: "该邮箱已存在，请更换邮箱后重试。"
  },
  USER_DISABLED: {
    summary: "当前账号已被禁用，请联系管理员。"
  },
  ROLE_NOT_FOUND: {
    summary: "所选角色不存在，请刷新页面后重试。"
  },
  KB_ACCESS_DENIED: {
    summary: "当前账号没有访问该知识库的权限。"
  },
  KB_ACCESS_NOT_FOUND: {
    summary: "未找到对应的知识库授权记录。",
    nextStep: "请刷新授权列表后重试。"
  },
  PASSWORD_TOO_WEAK: {
    summary: "密码强度不足，请使用更复杂的密码。"
  },
  EVAL_SET_NOT_FOUND: {
    summary: "评测集不存在或已被删除。",
    nextStep: "请刷新评测集列表后重试。"
  },
  EVAL_RUN_NOT_FOUND: {
    summary: "评测记录不存在或已失效。",
    nextStep: "请重新查询或重新发起评测。"
  },
  UNEXPECTED_ERROR: {
    summary: "服务内部异常，请稍后重试。"
  }
};

function resolveRequestIdFromHeaders(error: AxiosError): string | null {
  const pickText = (value: unknown): string | null => {
    if (typeof value === "string") {
      return value;
    }
    if (Array.isArray(value)) {
      const text = value.find((item) => typeof item === "string");
      return typeof text === "string" ? text : null;
    }
    return null;
  };

  const headers = error.response?.headers;
  if (!headers) {
    return null;
  }

  if (typeof headers.get === "function") {
    return pickText(headers.get("x-request-id") ?? headers.get("X-Request-ID"));
  }

  const record = headers as Record<string, unknown>;
  return pickText(record["x-request-id"] ?? record["X-Request-ID"]);
}

export function normalizeApiError(error: unknown): ApiErrorShape {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{
      error?: { code?: string; message?: string; detail?: unknown };
      request_id?: string | null;
    }>;
    const payload = axiosError.response?.data;
    const status = axiosError.response?.status;
    const fallbackCode = axiosError.response
      ? status && status >= 500
        ? "UNEXPECTED_ERROR"
        : "UNKNOWN_ERROR"
      : "NETWORK_ERROR";
    const fallbackMessage =
      fallbackCode === "NETWORK_ERROR" ? "网络连接失败" : "请求处理失败";
    const code = payload?.error?.code ?? fallbackCode;
    const message = payload?.error?.message ?? fallbackMessage;
    return {
      code,
      message,
      detail: payload?.error?.detail,
      request_id: payload?.request_id ?? resolveRequestIdFromHeaders(axiosError)
    };
  }
  if (
    error &&
    typeof error === "object" &&
    "code" in error &&
    "message" in error &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  ) {
    const record = error as {
      code: string;
      message: string;
      detail?: unknown;
      request_id?: string | null;
    };
    return {
      code: record.code,
      message: record.message,
      detail: record.detail,
      request_id: record.request_id ?? null
    };
  }
  if (error instanceof Error) {
    return {
      code: "UNKNOWN_ERROR",
      message: error.message
    };
  }
  return {
    code: "UNKNOWN_ERROR",
    message: "未知错误"
  };
}

export function resolveApiErrorDisplay(error: ApiErrorShape): ApiErrorDisplay {
  const mapped = API_ERROR_DISPLAY_MAP[error.code];
  if (mapped) {
    return mapped;
  }
  if (error.message.trim()) {
    return {
      summary: error.message
    };
  }
  return API_ERROR_DISPLAY_MAP.UNKNOWN_ERROR;
}

export function formatApiErrorMessage(error: ApiErrorShape): string {
  const display = resolveApiErrorDisplay(error);
  if (error.request_id) {
    return `${display.summary}（请求 ID：${error.request_id}）`;
  }
  return display.summary;
}
