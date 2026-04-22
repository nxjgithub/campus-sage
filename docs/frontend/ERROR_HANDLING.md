# ERROR_HANDLING.md — 前端错误处理规范

## 1. 目标
- 将后端统一错误结构转化为可理解、可定位、可恢复的前端体验。
- 避免“只提示失败”而不告诉用户下一步。

## 2. 错误分层
- 网络层错误
  - 断网、DNS、超时、跨域
- 协议层错误
  - HTTP 4xx/5xx
- 流式层错误
  - SSE 连接中断、事件解析失败、流内 `error` 事件
- 业务层错误
  - 后端 `error.code`（如 `KB_NOT_FOUND`、`VECTOR_SEARCH_FAILED`）
- 正常拒答
  - `200 + refusal=true`，不属于错误

## 3. Axios 拦截器规则
- 请求拦截
  - 自动附带 `X-Request-ID`（前端生成）
- 响应拦截
  - 若有 `error` 对象，统一提取：
    - `code`
    - `message`
    - `detail`
    - `request_id`

## 4. 全局错误提示策略
- 默认 toast：展示 `message`
- 可展开详情：展示 `code` 与 `request_id`
- 调试模式：展示 `detail` JSON

## 5. 关键错误码处理建议
- `VALIDATION_FAILED`
  - 就地标红表单项，提示用户修正输入
- `KB_NOT_FOUND` / `DOCUMENT_NOT_FOUND` / `INGEST_JOB_NOT_FOUND`
  - 跳转列表页并提示资源不存在
- 问答页遇到 `KB_NOT_FOUND` / `KB_ACCESS_DENIED`
  - 自动刷新知识库列表
  - 若当前知识库已失效，则切换到首个仍可用知识库
  - 清理失效会话上下文，并尽量保留用户刚输入的问题文本
- 问答页遇到 `CONVERSATION_NOT_FOUND`
  - 自动刷新当前知识库的会话列表
  - 清理失效会话上下文，避免继续向已删除会话发送请求
- `FILE_TYPE_NOT_ALLOWED`
  - 上传控件前置校验并提示仅支持 PDF
- `FILE_TOO_LARGE`
  - 读取后端 `detail.max_mb`，提示文件大小上限
- `INGEST_JOB_NOT_RETRYABLE`
  - 置灰重试按钮并提示当前状态不可重试
- `VECTOR_SEARCH_FAILED` / `VECTOR_UPSERT_FAILED`
  - 提示“向量服务不可用，请稍后重试”
- `RAG_MODEL_FAILED`
  - 提示“模型服务不可用”，保留当前问题文本供重试
- `UNEXPECTED_ERROR`
  - 提示“服务内部错误”，附 `request_id`

## 6. 重试策略
- 查询请求：可自动重试 1~2 次（指数退避）。
- 变更请求：默认不自动重试，避免重复提交。
- 用户触发“重试”时保留上次输入与上下文。

## 7. 拒答处理（非错误）
- 当 `refusal=true`：
  - 不显示红色错误条
  - 显示中性提示卡片：
    - 映射后的中文 `refusal_reason`
    - `suggestions[]`
    - 可复制的 `request_id`（放在次级信息区）
  - 若有弱相关引用，可照常展示

## 7.1 流式取消处理（非错误）
- 当 `error.code=CHAT_RUN_CANCELED` 或 `done.status=canceled`：
  - 不展示失败 toast
  - 将助手消息标记为“已取消生成”
  - 保留已生成 token 供用户继续查看
  - 允许用户直接再次发送

## 8. 观测与上报
- 每次错误日志至少记录：
  - `api_path`
  - `http_status`
  - `error.code`
  - `request_id`
- 前端埋点系统（如接入）禁止上传用户原始敏感文本。

## 9. 文案风格
- 中文、简洁、指向下一步动作。
- 示例：
  - 不推荐：“请求失败”
  - 推荐：“入库任务不存在，请刷新列表后重试（请求ID：req_xxx）”

## 上传错误补充（2026-03 第四轮）
- `FILE_TYPE_NOT_ALLOWED` 的提示文案应改为“当前仅支持 PDF、DOCX、HTML、Markdown、TXT”。
- 上传前提示与后端兜底需保持一致，避免前端放行但后端拒绝的错位体验。
# 2026-03 补充：后端异常文案映射

- 前端收到后端异常时，主提示文案必须优先根据 `error.code` 映射为用户可理解的中文提示。
- 未命中映射时，才回退展示后端返回的 `error.message`。
- `error.code` 不得作为 toast 或错误卡片主标题直接展示，只能出现在排障信息区。
- `request_id` 继续保留，用于定位问题；若页面需要展示技术细节，应与 `error.code` 一起放在次级信息区。
- 已知错误码应补充“下一步建议”，例如刷新列表、重新登录、稍后重试或检查输入。
