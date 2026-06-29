"""
会话管理 API

提供会话列表、查询、关闭、对话历史等接口。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from core.logging_utils import SESSION_END

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ── 响应模型 ──

class SessionInfo(BaseModel):
    session_id: str = Field(...)
    audience: str = Field(...)
    current_node: str = Field(...)
    connected: bool = Field(...)
    created_at: str = Field(...)
    message_count: int = Field(...)


class SessionDetail(SessionInfo):
    uptime_seconds: float = Field(...)
    last_emotion_label: str = Field(default="neutral")
    registered_tools: List[str] = Field(default_factory=list)
    active_timers: List[str] = Field(default_factory=list)


class MessageItem(BaseModel):
    role: str = Field(...)
    content: str = Field(...)


# ── 内部辅助 ──

def _get_sessions():
    """延迟导入，避免循环引用。"""
    from core.api.webrtc import get_active_sessions
    return get_active_sessions()


def _get_current_node(session) -> str:
    """Soul runtime keeps one active listening state."""
    return "active_listening"


def _get_runtime_session(session):
    from core.conversation.runtime_session import conversation_session_manager

    return conversation_session_manager.get(session.session_id)


def _get_messages(session) -> list:
    """Return recent conversation messages tracked by the runtime session."""
    runtime_session = _get_runtime_session(session)
    if runtime_session is not None:
        return list(runtime_session.recent_messages)
    return []


def _get_message_count(session) -> int:
    runtime_session = _get_runtime_session(session)
    if runtime_session is not None:
        return int(runtime_session.message_count)
    return 0


def _format_created_at(timestamp: float) -> str:
    """将 Unix 时间戳转为 ISO 8601 字符串。"""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


# ── 端点实现 ──

@router.get("", response_model=List[SessionInfo])
async def list_sessions() -> List[SessionInfo]:
    """列出所有活跃会话。"""
    sessions = _get_sessions()
    result = []
    for sid, session in sessions.items():
        messages = _get_messages(session)
        result.append(
            SessionInfo(
                session_id=session.session_id,
                audience=session.audience,
                current_node=_get_current_node(session),
                connected=session.connected,
                created_at=_format_created_at(session.created_at),
                message_count=_get_message_count(session),
            )
        )
    return result


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str) -> SessionDetail:
    """获取会话详情。"""
    sessions = _get_sessions()
    if session_id not in sessions:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found"
        )

    session = sessions[session_id]
    messages = _get_messages(session)
    uptime = time.time() - session.created_at

    return SessionDetail(
        session_id=session.session_id,
        audience=session.audience,
        current_node=_get_current_node(session),
        connected=session.connected,
        created_at=_format_created_at(session.created_at),
        message_count=_get_message_count(session),
        uptime_seconds=round(uptime, 1),
        last_emotion_label="neutral",       # Phase 2: 从 EmotionProcessor 状态读取
        registered_tools=["weather", "train_tickets", "train_ticket_price", "local_search"],
        active_timers=[],                    # Phase 2: 从 TimerManager 读取
    )


@router.delete("/{session_id}")
async def close_session(session_id: str) -> Dict[str, str]:
    """手动关闭会话（断开 WebRTC + 清理资源）。"""
    sessions = _get_sessions()
    if session_id not in sessions:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found"
        )

    session = sessions[session_id]

    # 1. 取消 PipelineTask（触发 WebRTC 断连 + 资源清理）
    try:
        await session.task.cancel()
    except Exception as e:
        logger.warning(f"[{SESSION_END}] | Task=会话关闭API | Error cancelling task for {session_id}: {e}")

    # 2. 从会话表中移除（_run_bot 的 cleanup 也会做，这里提前标记）
    session.connected = False

    logger.info(f"[{SESSION_END}] | Task=会话关闭API | Session manually closed: {session_id}")
    return {"status": "closed", "session_id": session_id}


@router.get("/{session_id}/history", response_model=List[MessageItem])
async def get_session_history(
    session_id: str, limit: int = 50
) -> List[MessageItem]:
    """获取会话对话历史。"""
    sessions = _get_sessions()
    if session_id not in sessions:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found"
        )

    session = sessions[session_id]
    messages = _get_messages(session)

    # 取最后 limit 条
    recent = messages[-limit:] if len(messages) > limit else messages

    return [
        MessageItem(role=m.get("role", "unknown"), content=m.get("content", ""))
        for m in recent
    ]
