"""问答相关路由。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.v1.deps import (
    get_authorization_service,
    get_chat_run_service,
    get_conversation_service,
    get_kb_service,
    get_optional_user,
    get_rag_service,
    require_permission,
)
from app.api.v1.mappers import rag_result_to_response
from app.api.v1.schemas.rag import (
    AskRequest,
    AskResponse,
    AskStreamRequest,
    ChatRunCancelResponse,
    ChatRunResponse,
    EditAndResendRequest,
    RegenerateRequest,
)
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import AuthorizationService
from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.ingest.service import KnowledgeBaseService
from app.rag.chat_run_service import ChatRunService
from app.rag.conversation_service import ConversationService
from app.rag.service import RagService

router = APIRouter(tags=["RAG"])
SSE_PING_INTERVAL_SECONDS = 10.0


@router.post("/kb/{kb_id}/ask", response_model=AskResponse)
def ask_question(
    request: Request,
    kb_id: str,
    payload: AskRequest,
    current_user: CurrentUser | None = Depends(get_optional_user),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: RagService = Depends(get_rag_service),
) -> AskResponse:
    """基于知识库进行问答。"""

    kb_record = kb_service.get(kb_id)
    _ensure_rag_permission(current_user)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=True,
    )
    filters = payload.filters.model_dump() if payload.filters else None
    result = service.ask(
        kb_id=kb_id,
        question=payload.question,
        request_id=request.state.request_id,
        conversation_id=payload.conversation_id,
        user_id=current_user.user.user_id if current_user else None,
        topk=payload.topk,
        threshold=payload.threshold,
        rerank_enabled=payload.rerank_enabled,
        filters=filters,
        debug=payload.debug,
    )
    return rag_result_to_response(result)


@router.post("/kb/{kb_id}/ask/stream")
async def ask_question_stream(
    request: Request,
    kb_id: str,
    payload: AskStreamRequest,
    current_user: CurrentUser | None = Depends(get_optional_user),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: RagService = Depends(get_rag_service),
    run_service: ChatRunService = Depends(get_chat_run_service),
) -> StreamingResponse:
    """基于知识库进行流式问答（SSE）。"""

    kb_record = kb_service.get(kb_id)
    user_id = current_user.user.user_id if current_user else None
    _ensure_rag_permission(current_user)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=True,
    )
    run = run_service.create_run(
        request_id=request.state.request_id,
        kb_id=kb_id,
        user_id=user_id,
        conversation_id=payload.conversation_id,
    )
    filters = payload.filters.model_dump() if payload.filters else None

    async def _event_stream() -> AsyncIterator[str]:
        done_sent = False
        final_status = "failed"
        conversation_id: str | None = None
        user_message_id: str | None = None
        assistant_message_id: str | None = None
        assistant_created_at: str | None = None
        disconnected = False
        stream_iterator = service.ask_stream(
            kb_id=kb_id,
            question=payload.question,
            request_id=request.state.request_id,
            conversation_id=payload.conversation_id,
            user_id=user_id,
            topk=payload.topk,
            threshold=payload.threshold,
            rerank_enabled=payload.rerank_enabled,
            filters=filters,
            debug=payload.debug,
            run_id=run.run_id,
            cancel_checker=lambda: disconnected or run_service.is_canceled(run.run_id),
        )
        next_event_task: asyncio.Task[tuple[bool, dict[str, object] | None]] | None = None
        try:
            next_event_task = asyncio.create_task(asyncio.to_thread(_next_stream_event, stream_iterator))
            while True:
                if await request.is_disconnected():
                    disconnected = True
                    final_status = "canceled"
                    if not run_service.is_canceled(run.run_id):
                        run_service.cancel_run(run.run_id)
                    break

                done, _ = await asyncio.wait(
                    {next_event_task},
                    timeout=SSE_PING_INTERVAL_SECONDS,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    yield _encode_sse(
                        "ping",
                        {
                            "run_id": run.run_id,
                            "request_id": request.state.request_id,
                        },
                    )
                    continue

                stream_ended, event = next_event_task.result()
                if stream_ended or event is None:
                    break
                next_event_task = asyncio.create_task(
                    asyncio.to_thread(_next_stream_event, stream_iterator)
                )
                event_name = str(event.get("event") or "token")
                event_data = dict(event.get("data") or {})
                event_data.setdefault("request_id", request.state.request_id)
                if event_name == "done":
                    done_sent = True
                    final_status = str(event_data.get("status") or "succeeded")
                    conversation_id = _to_optional_str(event_data.get("conversation_id"))
                    user_message_id = _to_optional_str(event_data.get("user_message_id"))
                    assistant_message_id = _to_optional_str(event_data.get("message_id"))
                    assistant_created_at = _to_optional_str(event_data.get("assistant_created_at"))
                yield _encode_sse(event_name, event_data)
        except AppError as exc:
            final_status = "failed"
            yield _encode_sse(
                "error",
                {
                    "run_id": run.run_id,
                    "code": exc.code.value,
                    "message": exc.message,
                    "detail": exc.detail,
                    "request_id": request.state.request_id,
                },
            )
        except Exception as exc:  # pragma: no cover - 兜底保护
            final_status = "failed"
            yield _encode_sse(
                "error",
                {
                    "run_id": run.run_id,
                    "code": ErrorCode.UNEXPECTED_ERROR.value,
                    "message": "流式生成失败",
                    "detail": {"error": str(exc)},
                    "request_id": request.state.request_id,
                },
            )
        finally:
            if next_event_task is not None and not next_event_task.done():
                next_event_task.cancel()
            if final_status == "succeeded":
                run_service.mark_succeeded(
                    run_id=run.run_id,
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    assistant_message_id=assistant_message_id,
                )
            elif final_status == "canceled":
                run_service.mark_canceled(
                    run_id=run.run_id,
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    assistant_message_id=assistant_message_id,
                )
            else:
                run_service.mark_failed(
                    run_id=run.run_id,
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    assistant_message_id=assistant_message_id,
                )
            if not done_sent:
                yield _encode_sse(
                    "done",
                    {
                        "run_id": run.run_id,
                        "status": final_status,
                        "conversation_id": conversation_id,
                        "user_message_id": user_message_id,
                        "message_id": assistant_message_id,
                        "assistant_created_at": assistant_created_at,
                        "request_id": request.state.request_id,
                    },
                )

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/chat/runs/{run_id}", response_model=ChatRunResponse)
def get_chat_run(
    request: Request,
    run_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.CONVERSATION_READ)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: ChatRunService = Depends(get_chat_run_service),
) -> ChatRunResponse:
    """获取流式运行状态。"""

    record = service.get_run(run_id)
    _ensure_chat_run_owner(current_user, record.user_id, run_id)
    _ensure_chat_run_kb_access(
        current_user=current_user,
        kb_id=record.kb_id,
        authz=authz,
        kb_service=kb_service,
    )
    return ChatRunResponse(
        run_id=record.run_id,
        kb_id=record.kb_id,
        conversation_id=record.conversation_id,
        user_message_id=record.user_message_id,
        assistant_message_id=record.assistant_message_id,
        status=record.status,
        cancel_flag=record.cancel_flag,
        started_at=record.started_at,
        finished_at=record.finished_at,
        request_id=request.state.request_id,
    )


@router.post("/chat/runs/{run_id}/cancel", response_model=ChatRunCancelResponse)
def cancel_chat_run(
    request: Request,
    run_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.MESSAGE_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: ChatRunService = Depends(get_chat_run_service),
) -> ChatRunCancelResponse:
    """取消流式生成。"""

    record = service.get_run(run_id)
    _ensure_chat_run_owner(current_user, record.user_id, run_id)
    _ensure_chat_run_kb_access(
        current_user=current_user,
        kb_id=record.kb_id,
        authz=authz,
        kb_service=kb_service,
    )
    record = service.cancel_run(run_id)
    return ChatRunCancelResponse(
        run_id=record.run_id,
        status=record.status,
        cancel_flag=record.cancel_flag,
        request_id=request.state.request_id,
    )


@router.post("/messages/{message_id}/regenerate", response_model=AskResponse)
def regenerate_message(
    request: Request,
    message_id: str,
    payload: RegenerateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MESSAGE_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    conversation_service: ConversationService = Depends(get_conversation_service),
    rag_service: RagService = Depends(get_rag_service),
) -> AskResponse:
    """重新生成回答。"""

    message = conversation_service.get_message(message_id)
    conversation = conversation_service.get_conversation(message.conversation_id)
    _ensure_conversation_owner(current_user, conversation.user_id, conversation.conversation_id)
    kb_record = kb_service.get(conversation.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=conversation.kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )
    source_user_message = _resolve_source_user_message(
        conversation_service=conversation_service,
        conversation_id=conversation.conversation_id,
        message=message,
    )
    filters = payload.filters.model_dump() if payload.filters else None
    result = rag_service.ask_for_existing_user_message(
        kb_id=conversation.kb_id,
        question=source_user_message.content,
        request_id=request.state.request_id,
        conversation_id=conversation.conversation_id,
        user_message_id=source_user_message.message_id,
        topk=payload.topk,
        threshold=payload.threshold,
        rerank_enabled=payload.rerank_enabled,
        filters=filters,
        debug=payload.debug,
    )
    return rag_result_to_response(result)


@router.post("/messages/{message_id}/edit-and-resend", response_model=AskResponse)
def edit_and_resend_message(
    request: Request,
    message_id: str,
    payload: EditAndResendRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MESSAGE_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    conversation_service: ConversationService = Depends(get_conversation_service),
    rag_service: RagService = Depends(get_rag_service),
) -> AskResponse:
    """编辑问题后重发（返回新分支会话）。"""

    message = conversation_service.get_message(message_id)
    conversation = conversation_service.get_conversation(message.conversation_id)
    _ensure_conversation_owner(current_user, conversation.user_id, conversation.conversation_id)
    kb_record = kb_service.get(conversation.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=conversation.kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )
    branch = conversation_service.create_conversation(
        kb_id=conversation.kb_id,
        user_id=current_user.user.user_id,
        title=payload.question.strip()[:50] if payload.question.strip() else None,
    )
    user_message = conversation_service.save_message(
        conversation_id=branch.conversation_id,
        role="user",
        content=payload.question,
        refusal=False,
        refusal_reason=None,
        timing=None,
        suggestions=None,
        next_steps=None,
        citations=None,
        request_id=request.state.request_id,
        edited_from_message_id=message_id,
    )
    filters = payload.filters.model_dump() if payload.filters else None
    result = rag_service.ask_for_existing_user_message(
        kb_id=branch.kb_id,
        question=payload.question,
        request_id=request.state.request_id,
        conversation_id=branch.conversation_id,
        user_message_id=user_message.message_id,
        topk=payload.topk,
        threshold=payload.threshold,
        rerank_enabled=payload.rerank_enabled,
        filters=filters,
        debug=payload.debug,
    )
    return rag_result_to_response(result)


def _ensure_rag_permission(current_user: CurrentUser | None) -> None:
    """校验问答权限。"""

    if current_user is None:
        return
    if Permission.RAG_ASK in current_user.permissions or "*" in current_user.permissions:
        return
    raise AppError(
        code=ErrorCode.AUTH_FORBIDDEN,
        message="权限不足",
        detail={"permission": Permission.RAG_ASK},
        status_code=403,
    )


def _ensure_conversation_owner(
    current_user: CurrentUser,
    conversation_user_id: str | None,
    conversation_id: str,
) -> None:
    """校验会话归属。"""

    if "*" in current_user.permissions:
        return
    if conversation_user_id != current_user.user.user_id:
        raise AppError(
            code=ErrorCode.AUTH_FORBIDDEN,
            message="无权访问该会话",
            detail={"conversation_id": conversation_id},
            status_code=403,
        )


def _ensure_chat_run_owner(current_user: CurrentUser, run_user_id: str | None, run_id: str) -> None:
    """校验聊天运行归属。"""

    if "*" in current_user.permissions:
        return
    if run_user_id != current_user.user.user_id:
        raise AppError(
            code=ErrorCode.AUTH_FORBIDDEN,
            message="无权访问该聊天运行",
            detail={"run_id": run_id},
            status_code=403,
        )


def _ensure_chat_run_kb_access(
    current_user: CurrentUser,
    kb_id: str | None,
    authz: AuthorizationService,
    kb_service: KnowledgeBaseService,
) -> None:
    """校验聊天运行关联知识库权限。"""

    if kb_id is None:
        return
    kb_record = kb_service.get(kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )


def _resolve_source_user_message(
    conversation_service: ConversationService,
    conversation_id: str,
    message,
):
    """解析重生成的来源用户消息。"""

    if message.role == "user":
        return message
    source_user_message = conversation_service.get_previous_user_message(
        conversation_id=conversation_id,
        before_message_id=message.message_id,
    )
    if source_user_message is None:
        raise AppError(
            code=ErrorCode.VALIDATION_FAILED,
            message="未找到可重生成的用户消息",
            detail={"message_id": message.message_id},
            status_code=400,
        )
    return source_user_message


def _encode_sse(event: str, data: dict[str, object]) -> str:
    """编码 SSE 事件。"""

    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _next_stream_event(
    stream_iterator: Iterator[dict[str, object]],
) -> tuple[bool, dict[str, object] | None]:
    """拉取下一条流式事件。"""

    try:
        return False, next(stream_iterator)
    except StopIteration:
        return True, None


def _to_optional_str(value: object) -> str | None:
    """将对象转换为可选字符串。"""

    if value is None:
        return None
    return str(value)
