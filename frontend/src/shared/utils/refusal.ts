export function formatRefusalReason(reason?: string | null) {
  if (reason === "NO_EVIDENCE") {
    return "未检索到可用证据";
  }
  if (reason === "LOW_SCORE") {
    return "命中证据相关性不足";
  }
  if (reason === "LOW_EVIDENCE") {
    return "证据内容不足以支撑回答";
  }
  if (reason === "LOW_COVERAGE") {
    return "问题缺少足够上下文";
  }
  return reason ?? "等待补充更多信息";
}
