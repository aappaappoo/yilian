"""LiveKit voice room token and agent dispatch routes."""

from __future__ import annotations

import json
import time
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

import jwt
from fastapi import APIRouter, HTTPException, Request
from livekit import api as livekit_api
from loguru import logger
from pydantic import BaseModel, Field

from core.config import settings
from core.conversation.sql_store import SQLStore
from core.logging_utils import SESSION_END, SESSION_START, STARTUP

router = APIRouter(prefix="/api", tags=["voice"])

_sessions: Dict[str, "SessionRecord"] = {}
_sql_store: Optional[SQLStore] = None


def set_sql_store(sql_store: Optional[SQLStore]) -> None:
    global _sql_store
    _sql_store = sql_store


class SessionRecord:
    """Runtime record for a LiveKit voice session dispatched to an agent worker."""

    def __init__(
        self,
        *,
        session_id: str,
        audience: str,
        room_name: str,
        participant_identity: str,
        conversation_id: str = "",
        user_id: str = "",
        client_ip: str = "",
    ) -> None:
        self.session_id = session_id
        self.audience = audience
        self.room_name = room_name
        self.participant_identity = participant_identity
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.client_ip = client_ip
        self.connected = True
        self.created_at = time.time()


class LiveKitTokenRequest(BaseModel):
    audience: str = Field(default="Liyin", description="人群标识")
    session_id: Optional[str] = Field(default=None, description="已有会话 ID（继续对话用）")
    conversation_id: Optional[str] = Field(default=None, description="长期对话容器 ID")
    room_name: Optional[str] = Field(default=None, description="LiveKit 房间名，默认按 session_id 生成")
    participant_identity: Optional[str] = Field(default=None, description="前端用户 identity")
    token: Optional[str] = Field(default=None, description="JWT 认证 Token（用于提取 user_id）")


class LiveKitTokenResponse(BaseModel):
    url: str = Field(..., description="LiveKit WebSocket URL")
    token: str = Field(..., description="前端加入房间用的 LiveKit token")
    room_name: str = Field(..., description="LiveKit 房间名")
    session_id: str = Field(..., description="业务会话 ID")
    conversation_id: str = Field(default="", description="长期对话容器 ID")
    participant_identity: str = Field(..., description="前端用户 identity")


class StatusResponse(BaseModel):
    session_id: str = Field(...)
    audience: str = Field(...)
    current_node: str = Field(...)
    connected: bool = Field(...)
    uptime_seconds: float = Field(...)


def _extract_client_ip(request: Optional[Request]) -> str:
    if request is None:
        return ""
    for header in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
        value = request.headers.get(header, "")
        if not value:
            continue
        ip = value.split(",", 1)[0].strip()
        if ip:
            return ip
    if request.client is None:
        return ""
    return request.client.host or ""


def _extract_user_id_from_token(token: str) -> str:
    if not token:
        return ""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        return str(payload.get("sub") or "")
    except jwt.ExpiredSignatureError:
        logger.warning(f"[{SESSION_START}] | Task=JWT解析 | JWT Token 已过期，user_id 将为空")
    except jwt.InvalidTokenError:
        logger.warning(f"[{SESSION_START}] | Task=JWT解析 | JWT Token 无效，user_id 将为空")
    return ""


def _make_livekit_room_name(session_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in session_id)
    return f"soulmeet-{safe[:80]}"


def _make_livekit_token(*, identity: str, room_name: str, name: str) -> str:
    if not settings.livekit_api_key or not settings.livekit_api_secret:
        raise HTTPException(status_code=503, detail="LiveKit API key/secret is not configured")
    return (
        livekit_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(name)
        .with_ttl(timedelta(seconds=settings.livekit_token_ttl_seconds))
        .with_grants(
            livekit_api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )


async def _ensure_runtime_conversation_id(
    *,
    conversation_id: str,
    user_id: str,
    audience: str,
    session_id: str,
) -> str:
    if _sql_store is None:
        return conversation_id
    try:
        conversation = await _sql_store.ensure_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            audiences=audience,
            session_id=session_id,
            title="新对话" if user_id else "访客对话",
            status="active" if user_id else "guest",
        )
        return str(conversation["conversation_id"])
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


async def _dispatch_voice_agent(*, room_name: str, metadata: Dict[str, Any]) -> None:
    if not settings.livekit_url:
        raise HTTPException(status_code=503, detail="LiveKit URL is not configured")
    if not settings.livekit_api_key or not settings.livekit_api_secret:
        raise HTTPException(status_code=503, detail="LiveKit API key/secret is not configured")

    lkapi = livekit_api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        rooms = await lkapi.room.list_rooms(livekit_api.ListRoomsRequest(names=[room_name]))
        if not rooms.rooms:
            await lkapi.room.create_room(
                livekit_api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=300,
                    departure_timeout=30,
                )
            )
            logger.info(f"[{SESSION_START}] | Task=LiveKitRoom创建 | room={room_name}")

        existing = await lkapi.agent_dispatch.list_dispatch(room_name)
        for dispatch in existing:
            if getattr(dispatch, "agent_name", "") == settings.voice_agent_name:
                logger.info(
                    f"[{SESSION_START}] | Task=LiveKitAgent复用 | "
                    f"room={room_name}, agent={settings.voice_agent_name}"
                )
                return

        await lkapi.agent_dispatch.create_dispatch(
            livekit_api.CreateAgentDispatchRequest(
                agent_name=settings.voice_agent_name,
                room=room_name,
                metadata=json.dumps(metadata, ensure_ascii=False),
            )
        )
        logger.info(
            f"[{SESSION_START}] | Task=LiveKitAgent派发 | "
            f"room={room_name}, agent={settings.voice_agent_name}, session={metadata.get('session_id')}"
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"[{SESSION_START}] | Task=LiveKitAgent派发 | 派发失败: "
            f"room={room_name}, agent={settings.voice_agent_name}, error={exc}"
        )
        raise HTTPException(status_code=502, detail=f"LiveKit agent dispatch failed: {exc}") from exc
    finally:
        await lkapi.aclose()


@router.post("/livekit/token", response_model=LiveKitTokenResponse)
async def create_livekit_token(
    http_request: Request,
    request: LiveKitTokenRequest,
) -> LiveKitTokenResponse:
    requested_session = request.session_id or "<new>"
    logger.info(
        f"[{SESSION_START}] | Task=LiveKitToken请求 | audience={request.audience}, "
        f"session={requested_session}, participant={request.participant_identity or '<auto>'}"
    )
    if not settings.livekit_url:
        logger.error(
            f"[{STARTUP}] | Task=LiveKit配置检查 | LIVEKIT_URL未配置，无法签发token: "
            f"session={requested_session}"
        )
        raise HTTPException(status_code=503, detail="LiveKit URL is not configured")

    session_id = request.session_id or str(uuid.uuid4())
    room_name = request.room_name or _make_livekit_room_name(session_id)
    participant_identity = request.participant_identity or f"user-{uuid.uuid4().hex[:12]}"
    user_id = _extract_user_id_from_token(request.token or "")
    client_ip = _extract_client_ip(http_request)
    conversation_id = await _ensure_runtime_conversation_id(
        conversation_id=request.conversation_id or "",
        user_id=user_id,
        audience=request.audience,
        session_id=session_id,
    )

    frontend_token = _make_livekit_token(
        identity=participant_identity,
        room_name=room_name,
        name=participant_identity,
    )
    await _dispatch_voice_agent(
        room_name=room_name,
        metadata={
            "session_id": session_id,
            "conversation_id": conversation_id,
            "audience": request.audience,
            "user_id": user_id,
            "client_ip": client_ip,
            "participant_identity": participant_identity,
        },
    )

    _sessions[session_id] = SessionRecord(
        session_id=session_id,
        audience=request.audience,
        room_name=room_name,
        participant_identity=participant_identity,
        conversation_id=conversation_id,
        user_id=user_id,
        client_ip=client_ip,
    )
    logger.info(
        f"[{SESSION_START}] | Task=LiveKitToken签发 | session={session_id}, "
        f"room={room_name}, participant={participant_identity}, agent={settings.voice_agent_name}"
    )
    return LiveKitTokenResponse(
        url=settings.livekit_url,
        token=frontend_token,
        room_name=room_name,
        session_id=session_id,
        conversation_id=conversation_id,
        participant_identity=participant_identity,
    )


@router.get("/status/{session_id}", response_model=StatusResponse)
async def get_session_status(session_id: str) -> StatusResponse:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    uptime = time.time() - session.created_at
    return StatusResponse(
        session_id=session.session_id,
        audience=session.audience,
        current_node="active_listening",
        connected=session.connected,
        uptime_seconds=round(uptime, 1),
    )


def close_active_session(session_id: str) -> bool:
    session = _sessions.pop(session_id, None)
    if session is None:
        return False
    session.connected = False
    logger.info(f"[{SESSION_END}] | Task=LiveKit会话关闭 | session={session_id}")
    return True


def get_active_sessions() -> Dict[str, SessionRecord]:
    return _sessions


async def send_livekit_app_data(session_id: str, payload: Dict[str, Any]) -> bool:
    record = _sessions.get(session_id)
    if record is None:
        return False
    if not settings.livekit_url or not settings.livekit_api_key or not settings.livekit_api_secret:
        return False

    lkapi = livekit_api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        await lkapi.room.send_data(
            livekit_api.SendDataRequest(
                room=record.room_name,
                data=data,
                kind=livekit_api.DataPacket.Kind.RELIABLE,
            )
        )
        return True
    except Exception as exc:
        logger.warning(
            f"[{SESSION_START}] | Task=LiveKit数据发送 | 失败: "
            f"session={session_id[:8]}, room={record.room_name}, "
            f"type={payload.get('type')}, error={exc}"
        )
        return False
    finally:
        await lkapi.aclose()
