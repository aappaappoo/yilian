"""HTTP text input adapter for the unified conversation runtime."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from core.config import settings
from core.conversation.runtime_session import conversation_session_manager
from core.conversation.sql_store import SQLStore
from core.logging_utils import AI_REPLY, SESSION_END, SESSION_START, USER_INPUT, flatten_content

router = APIRouter(prefix="/api/text-runtime", tags=["text-runtime"])
_sql_store: Optional[SQLStore] = None


def set_sql_store(sql_store: Optional[SQLStore]) -> None:
    global _sql_store
    _sql_store = sql_store


class TextRuntimeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    audience: str = Field(default="Aini")
    session_id: Optional[str] = Field(default=None)
    conversation_id: Optional[str] = Field(default=None)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=120.0)
    token: Optional[str] = Field(default=None)
    voice_broadcast_enabled: Optional[bool] = Field(default=None)


class TextRuntimeInterruptRequest(BaseModel):
    audience: str = Field(default="Aini")
    conversation_id: Optional[str] = Field(default=None)
    token: Optional[str] = Field(default=None)


class TextRuntimeTaskRetryRequest(BaseModel):
    audience: str = Field(default="Aini")
    conversation_id: Optional[str] = Field(default=None)
    token: Optional[str] = Field(default=None)
    retry_token: str = Field(..., min_length=1)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=120.0)


class TextRuntimeResponse(BaseModel):
    session_id: str
    conversation_id: str
    audience: str
    message_id: Optional[str] = None
    text: str
    source: str = "text-runtime"
    first_token_at: Optional[str] = None
    artifact: Optional[dict[str, Any]] = None


class TextRuntimeTaskRetryResponse(BaseModel):
    ok: bool
    accepted: bool
    session_id: str
    conversation_id: str
    audience: str
    route_status: str
    text: str = ""
    source: str = "task_retry"
    artifact: Optional[dict[str, Any]] = None


class TextRuntimeStateMessage(BaseModel):
    role: str
    content: str


class TextRuntimeStateResponse(BaseModel):
    session_id: str
    conversation_id: str
    audience: str
    active: bool
    message_count: int
    latest_event_seq: int = 0
    messages: list[TextRuntimeStateMessage] = Field(default_factory=list)


def _sse_payload(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _extract_client_ip(request: Optional[Request]) -> str:
    if request is None:
        return ""
    for header in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
        value = request.headers.get(header, "")
        if value:
            return value.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def _extract_user_id(token: str) -> str:
    if not token:
        return ""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        return payload.get("sub", "") or ""
    except jwt.ExpiredSignatureError:
        logger.warning(f"[{SESSION_START}] | Task=HTTP文本Runtime | JWT Token 已过期，user_id 为空")
    except jwt.InvalidTokenError:
        logger.warning(f"[{SESSION_START}] | Task=HTTP文本Runtime | JWT Token 无效，user_id 为空")
    return ""


@router.post("/message", response_model=TextRuntimeResponse)
async def text_runtime_message(
    http_request: Request,
    request: TextRuntimeRequest,
) -> TextRuntimeResponse:
    audience = request.audience.strip() or settings.audience
    client_ip = _extract_client_ip(http_request)
    user_id = _extract_user_id(request.token or "")
    conversation_id = (request.conversation_id or "").strip()
    if _sql_store is not None:
        try:
            status_value = "active" if user_id else "guest"
            conversation = await _sql_store.ensure_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                audiences=audience,
                session_id=request.session_id or "",
                title="新对话" if user_id else "访客对话",
                status=status_value,
            )
            conversation_id = conversation["conversation_id"]
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    logger.info(
        f"[{USER_INPUT}] | Task=HTTP文本入口 | audience={audience}, "
        f"session={request.session_id[:8] if request.session_id else '<new>'}, "
        f"conversation={conversation_id[:8] if conversation_id else '<none>'}, "
        f"user_id={'已绑定' if user_id else '<空>'}, client_ip={client_ip or '<空>'}, "
        f"text='{flatten_content(request.text, max_len=80)}'"
    )
    session = await conversation_session_manager.get_or_create(
        audience=audience,
        session_id=request.session_id,
        conversation_id=conversation_id,
        user_id=user_id,
        client_ip=client_ip,
    )
    if request.voice_broadcast_enabled is not None:
        conversation_session_manager.set_voice_reply_enabled(
            session.session_id,
            bool(request.voice_broadcast_enabled),
        )
    loop = asyncio.get_running_loop()
    http_reply_future: asyncio.Future = loop.create_future()
    session.pending_http_replies.append(http_reply_future)

    async def run_text_response() -> None:
        try:
            await conversation_session_manager.handle_user_text(
                session,
                request.text,
                timeout_seconds=request.timeout_seconds,
                source="text",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if http_reply_future in session.pending_http_replies and not http_reply_future.done():
                http_reply_future.set_exception(exc)
            logger.exception(
                f"[{AI_REPLY}] | Task=HTTP文本后台任务失败 | "
                f"session={session.session_id[:8]}, error={exc}"
            )

    response_task = asyncio.create_task(run_text_response())
    session.background_response_tasks.add(response_task)
    response_task.add_done_callback(session.background_response_tasks.discard)

    try:
        reply_text, source, artifact, first_token_at, message_id = await asyncio.wait_for(
            asyncio.shield(http_reply_future),
            timeout=request.timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        logger.warning(
            f"[{AI_REPLY}] | Task=HTTP文本出口超时 | session={session.session_id[:8]}, "
            f"timeout={request.timeout_seconds}s, background_task_running={not response_task.done()}"
        )
        raise HTTPException(status_code=504, detail="文本回复等待超时，后台仍在处理。") from exc
    except asyncio.CancelledError:
        logger.info(
            f"[{AI_REPLY}] | Task=HTTP文本出口断开 | session={session.session_id[:8]}, "
            f"background_task_running={not response_task.done()}"
        )
        raise
    finally:
        if http_reply_future in session.pending_http_replies:
            session.pending_http_replies.remove(http_reply_future)
    logger.info(
        f"[{AI_REPLY}] | Task=HTTP文本出口 | session={session.session_id[:8]}, "
        f"message_id={message_id}, source={source}, text='{flatten_content(reply_text, max_len=80)}'"
    )
    return TextRuntimeResponse(
        session_id=session.session_id,
        conversation_id=session.conversation_id,
        audience=session.audience,
        message_id=message_id,
        text=reply_text,
        source=source,
        first_token_at=first_token_at,
        artifact=artifact,
    )


@router.post("/session/{session_id}/interrupt")
async def interrupt_text_runtime_session(
    session_id: str,
    request: TextRuntimeInterruptRequest,
) -> dict[str, bool]:
    user_id = _extract_user_id(request.token or "")
    logger.info(
        f"[{AI_REPLY}] | Task=HTTP文本中断 | session={session_id[:8]}, "
        f"audience={request.audience}, user_id={'已绑定' if user_id else '<空>'}"
    )
    interrupted = await conversation_session_manager.interrupt_session_response(
        session_id,
        reason="user_stop_button",
    )
    return {"ok": True, "interrupted": interrupted}


@router.post("/session/{session_id}/task-retry", response_model=TextRuntimeTaskRetryResponse)
async def retry_text_runtime_task(
    session_id: str,
    http_request: Request,
    request: TextRuntimeTaskRetryRequest,
) -> TextRuntimeTaskRetryResponse:
    del http_request, request
    logger.info(
        f"[{USER_INPUT}] | Task=HTTP文本任务重试 | session={session_id[:8]}, route_removed=true"
    )
    raise HTTPException(status_code=410, detail="旧任务重试接口已移除")


@router.get("/events/{session_id}")
async def text_runtime_events(
    session_id: str,
    http_request: Request,
    audience: str = "Aini",
    token: Optional[str] = None,
    conversation_id: Optional[str] = None,
    since: int = 0,
    replay: bool = False,
) -> StreamingResponse:
    audience_name = audience.strip() or settings.audience
    client_ip = _extract_client_ip(http_request)
    user_id = _extract_user_id(token or "")
    cid = (conversation_id or "").strip()
    if _sql_store is not None and cid:
        try:
            await _sql_store.ensure_conversation(
                conversation_id=cid,
                user_id=user_id,
                audiences=audience_name,
                session_id=session_id,
                title="新对话" if user_id else "访客对话",
                status="active" if user_id else "guest",
            )
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    session = await conversation_session_manager.get_or_create(
        audience=audience_name,
        session_id=session_id,
        conversation_id=cid,
        user_id=user_id,
        client_ip=client_ip,
    )
    queue = session.add_text_progress_subscriber()
    logger.info(
        f"[{SESSION_START}] | Task=HTTP文本进度订阅 | session={session.session_id[:8]}, "
        f"audience={session.audience}, subscribers={len(session.text_progress_subscribers)}"
    )

    async def event_stream():
        try:
            yield _sse_payload({"type": "text_progress_connected", "session_id": session.session_id})
            if replay or since > 0:
                for payload in list(session.text_event_history):
                    seq = int(payload.get("_seq") or 0)
                    if seq > since:
                        yield _sse_payload(payload)
            while True:
                if await http_request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _sse_payload(payload)
        finally:
            session.remove_text_progress_subscriber(queue)
            logger.info(
                f"[{SESSION_END}] | Task=HTTP文本进度退订 | session={session.session_id[:8]}, "
                f"subscribers={len(session.text_progress_subscribers)}"
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/session/{session_id}/state", response_model=TextRuntimeStateResponse)
async def get_text_runtime_state(
    session_id: str,
    request: Request,
    audience: str = "Aini",
    token: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> TextRuntimeStateResponse:
    audience_name = audience.strip() or settings.audience
    client_ip = _extract_client_ip(request)
    user_id = _extract_user_id(token or "")
    session = await conversation_session_manager.get_or_create(
        audience=audience_name,
        session_id=session_id,
        conversation_id=(conversation_id or "").strip(),
        user_id=user_id,
        client_ip=client_ip,
    )
    active_task = session.active_response_task
    return TextRuntimeStateResponse(
        session_id=session.session_id,
        conversation_id=session.conversation_id,
        audience=session.audience,
        active=bool(active_task and not active_task.done()),
        message_count=session.message_count,
        latest_event_seq=session.text_event_seq,
        messages=[
            TextRuntimeStateMessage(
                role=str(message.get("role") or ""),
                content=str(message.get("content") or ""),
            )
            for message in session.recent_messages[-50:]
        ],
    )


@router.delete("/session/{session_id}")
async def delete_text_runtime_session(
    session_id: str,
    preserve_db: bool = False,
) -> dict[str, bool | int]:
    logger.info(f"[{SESSION_END}] | Task=HTTP文本会话关闭 | session={session_id[:8]}")
    deleted_rows = 0
    conversation_session_manager.retire_session_id(session_id)
    await conversation_session_manager.close_session(session_id)
    if _sql_store is not None and not preserve_db:
        deleted_rows = await _sql_store.soft_delete_session(session_id)
    return {"ok": True, "soft_deleted_rows": deleted_rows, "preserved_db": preserve_db}
