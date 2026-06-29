"""
WebRTC signaling 路由

提供 WebRTC SDP offer/answer 交换接口。

每个新的 offer 创建一个新的会话（Pipeline 实例）。
底座负责：创建 connection → transport → pipeline → task
不含任何人群特有逻辑（遵循底座零业务污染原则）。
"""

from __future__ import annotations
import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

import jwt
from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from core.logging_utils import SESSION_START, SESSION_END, USER_INPUT, STARTUP
from pydantic import BaseModel, Field

from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.frames.frames import TranscriptionFrame

from core.config import settings
from core.conversation.runtime_session import SessionContext, conversation_session_manager
from core.conversation.sql_store import SQLStore
from core.pipeline.factory import build_pipeline
from core.api.voice_clone import get_active_cloned_voice_config
from core.persona.schema import load_persona

router = APIRouter(prefix="/api", tags=["webrtc"])

# ICE 服务器配置（STUN + 可选 TURN）
# TURN 通过环境变量 TURN_URL / TURN_USERNAME / TURN_CREDENTIAL 配置
ice_servers = [
    IceServer(urls="stun:stun.l.google.com:19302"),
]
if settings.turn_url and settings.turn_username and settings.turn_credential:
    ice_servers.append(
        IceServer(
            urls=settings.turn_url,
            username=settings.turn_username,
            credential=settings.turn_credential,
        )
    )
    logger.info(f"[{STARTUP}] | Task=ICE配置 | TURN 服务器已配置: {settings.turn_url}")

# ── 会话存储（进程内，所有活跃连接） ──
# key: session_id, value: SessionRecord
_sessions: Dict[str, "SessionRecord"] = {}

# key: pc_id, value: SmallWebRTCConnection（用于重连）
_pcs_map: Dict[str, SmallWebRTCConnection] = {}

# 保持后台 task 引用，防止被 GC 回收导致异常吞没
_background_tasks: Dict[str, asyncio.Task] = {}
_sql_store: Optional[SQLStore] = None


def set_sql_store(sql_store: Optional[SQLStore]) -> None:
    global _sql_store
    _sql_store = sql_store


class LiveKitDataConnection:
    """Small adapter that gives LiveKit data messages the same sync API as SmallWebRTC."""

    def __init__(self, transport: LiveKitTransport, loop: asyncio.AbstractEventLoop):
        self._transport = transport
        self._loop = loop
        self.pc_id = f"livekit:{transport.participant_id or 'pending'}"

    def refresh_participant_id(self) -> None:
        self.pc_id = f"livekit:{self._transport.participant_id or 'pending'}"

    def send_app_message(self, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        client = getattr(self._transport, "_client", None)
        if client is None:
            logger.warning(
                f"[{SESSION_START}] | Task=LiveKit数据发送 | client未就绪，跳过发送: "
                f"pc_id={self.pc_id}, payload_type={payload.get('type', '<unknown>')}"
            )
            return
        task = self._loop.create_task(client.send_data(data))

        def _log_send_result(t: asyncio.Task) -> None:
            if t.cancelled():
                logger.warning(
                    f"[{SESSION_END}] | Task=LiveKit数据发送 | 发送任务被取消: "
                    f"pc_id={self.pc_id}, payload_type={payload.get('type', '<unknown>')}"
                )
            elif t.exception() is not None:
                logger.warning(
                    f"[{SESSION_START}] | Task=LiveKit数据发送 | 发送失败: "
                    f"pc_id={self.pc_id}, payload_type={payload.get('type', '<unknown>')}, error={t.exception()}"
                )

        task.add_done_callback(_log_send_result)


def _extract_client_ip(request: Optional[Request]) -> str:
    """Extract a best-effort client IP for location confirmation."""
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


async def _cleanup_webrtc_connection(connection: SmallWebRTCConnection, reason: str) -> None:
    """Best-effort cleanup for a WebRTC connection that failed before a session exists."""
    _pcs_map.pop(connection.pc_id, None)
    try:
        await connection.disconnect()
    except asyncio.CancelledError:
        logger.warning(
            f"[{SESSION_START}] | Task=WebRTC资源清理 | disconnect 被取消: pc_id={connection.pc_id}, reason={reason}"
        )
    except Exception as exc:
        logger.warning(
            f"[{SESSION_START}] | Task=WebRTC资源清理 | disconnect 失败: pc_id={connection.pc_id}, reason={reason}, error={exc}"
        )

    try:
        await connection.cleanup()
    except asyncio.CancelledError:
        logger.warning(
            f"[{SESSION_START}] | Task=WebRTC资源清理 | cleanup 被取消: pc_id={connection.pc_id}, reason={reason}"
        )
    except Exception as exc:
        logger.warning(
            f"[{SESSION_START}] | Task=WebRTC资源清理 | cleanup 失败: pc_id={connection.pc_id}, reason={reason}, error={exc}"
        )


async def _initialize_webrtc_with_retry(request: OfferRequest) -> SmallWebRTCConnection:
    """
    Initialize a WebRTC connection and retry once when aiortc/aioice cancels during negotiation.

    The observed 500 comes from asyncio.CancelledError inside aioice mDNS cleanup while
    setRemoteDescription() is running. In Python 3.11 this does not inherit Exception, so it
    bypasses the generic handler unless caught explicitly.
    """
    requested_pc_id = request.pc_id
    if requested_pc_id and requested_pc_id in _pcs_map:
        first_connection = _pcs_map[requested_pc_id]
        logger.info(
            f"[{SESSION_START}] | Task=WebRTC offer接收 | 复用已有 PeerConnection: pc_id={requested_pc_id}"
        )
    else:
        first_connection = SmallWebRTCConnection(ice_servers=ice_servers)
        _pcs_map[first_connection.pc_id] = first_connection

    try:
        await first_connection.initialize(sdp=request.sdp, type=request.type)
        return first_connection
    except asyncio.CancelledError as exc:
        logger.warning(
            f"[{SESSION_START}] | Task=WebRTC offer接收 | 初始化被取消，准备清理并重试: "
            f"pc_id={first_connection.pc_id}, error={exc}"
        )
        await _cleanup_webrtc_connection(first_connection, "initialize_cancelled")
    except Exception:
        await _cleanup_webrtc_connection(first_connection, "initialize_failed")
        raise

    retry_connection = SmallWebRTCConnection(ice_servers=ice_servers)
    _pcs_map[retry_connection.pc_id] = retry_connection
    try:
        await retry_connection.initialize(sdp=request.sdp, type=request.type)
        logger.info(
            f"[{SESSION_START}] | Task=WebRTC offer接收 | 初始化重试成功: pc_id={retry_connection.pc_id}"
        )
        return retry_connection
    except asyncio.CancelledError as exc:
        await _cleanup_webrtc_connection(retry_connection, "initialize_retry_cancelled")
        logger.error(
            f"[{SESSION_START}] | Task=WebRTC offer接收 | 初始化重试仍被取消: error={exc}"
        )
        raise HTTPException(status_code=503, detail="WebRTC negotiation was cancelled, please retry")
    except Exception:
        await _cleanup_webrtc_connection(retry_connection, "initialize_retry_failed")
        raise


class SessionRecord:
    """一个活跃会话的运行时记录。"""

    def __init__(
            self,
            session_id: str,
            audience: str,
            pc_id: str,
            task: PipelineTask,
            components: Optional[Any] = None,
            session_ctx: Optional[SessionContext] = None,
            client_ip: str = "",
    ):
        self.session_id = session_id
        self.audience = audience
        self.pc_id = pc_id
        self.task = task
        self.components = components
        self.session_ctx = session_ctx
        self.connected = True
        self.created_at = time.time()
        self.pending_http_replies: List[asyncio.Future] = []
        self.client_ip = client_ip


# ── 请求/响应模型 ──
class OfferRequest(BaseModel):
    sdp: str = Field(..., description="SDP(会话描述协议) offer 字符串")
    type: str = Field(default="offer", description="SDP 类型")
    audience: str = Field(default="Liyin", description="人群标识")
    pc_id: Optional[str] = Field(default=None, description="已有连接 ID（重连用）")
    session_id: Optional[str] = Field(default=None, description="已有会话 ID（重连并恢复上下文用）")
    conversation_id: Optional[str] = Field(default=None, description="长期对话容器 ID")
    token: Optional[str] = Field(default=None, description="JWT 认证 Token（用于提取 user_id）")


class OfferResponse(BaseModel):
    sdp: str = Field(..., description="SDP answer 字符串")
    type: str = Field(default="answer", description="SDP 类型")
    session_id: str = Field(..., description="会话 ID")
    conversation_id: str = Field(default="", description="长期对话容器 ID")
    pc_id: str = Field(..., description="PeerConnection ID")


class StatusResponse(BaseModel):
    session_id: str = Field(...)
    audience: str = Field(...)
    current_node: str = Field(...)
    connected: bool = Field(...)
    uptime_seconds: float = Field(...)


class IceServerResponse(BaseModel):
    urls: str = Field(..., description="ICE 服务器 URL")
    username: Optional[str] = Field(default=None, description="TURN 用户名")
    credential: Optional[str] = Field(default=None, description="TURN 密码")


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


@router.get("/ice-servers")
async def get_ice_servers() -> list[dict]:
    """
    返回 ICE 服务器配置（供前端创建 RTCPeerConnection 使用）。
    包含 STUN 和可选的 TURN 服务器信息。
    """
    result = []
    for server in ice_servers:
        entry: dict = {"urls": server.urls}
        if server.username:
            entry["username"] = server.username
        if server.credential:
            entry["credential"] = server.credential
        result.append(entry)
    return result


# 回调工厂（供外部注入 on_connected 行为，如触发问候语）
# main.py 可通过 set_on_connected_callback 注入
_on_connected_callback: Optional[
    Callable[[PipelineTask, list, Any], Coroutine[Any, Any, None]]
] = None


def set_on_connected_callback(
        cb: Callable[[PipelineTask, list, Any], Coroutine[Any, Any, None]],
) -> None:
    """
    设置客户端连接后的回调。

    main.py 在启动时调用此函数注入问候行为，
    使 webrtc.py 不包含任何人群文案（底座零业务污染）。

    Args:
        cb: async def callback(task, messages, persona=None) -> None
    """
    global _on_connected_callback
    _on_connected_callback = cb


def _load_audience_persona(audience: str) -> Any:
    safe = str(audience or "").strip()
    if not safe or "/" in safe or "\\" in safe or ".." in safe:
        return None
    path = Path(__file__).resolve().parents[2] / "audiences" / safe / "persona.yaml"
    if not path.exists():
        return None
    try:
        return load_persona(path)
    except Exception as exc:
        logger.warning(f"[{STARTUP}] | Task=Persona加载 | 加载失败: audience={safe}, error={exc}")
        return None


def _extract_user_id_from_token(token: str) -> str:
    if not token:
        return ""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        return payload.get("sub", "")
    except jwt.ExpiredSignatureError:
        logger.warning(f"[{SESSION_START}] | Task=JWT解析 | JWT Token 已过期，user_id 将为空")
    except jwt.InvalidTokenError:
        logger.warning(f"[{SESSION_START}] | Task=JWT解析 | JWT Token 无效，user_id 将为空")
    return ""


def _make_livekit_token(
        *,
        identity: str,
        room_name: str,
        name: str,
) -> str:
    if not settings.livekit_api_key or not settings.livekit_api_secret:
        raise HTTPException(status_code=503, detail="LiveKit API key/secret is not configured")
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=settings.livekit_token_ttl_seconds)
    payload = {
        "iss": settings.livekit_api_key,
        "sub": identity,
        "name": name,
        "nbf": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "video": {
            "roomJoin": True,
            "room": room_name,
            "canPublish": True,
            "canSubscribe": True,
            "canPublishData": True,
        },
    }
    return jwt.encode(payload, settings.livekit_api_secret, algorithm="HS256")


def _make_livekit_room_name(session_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in session_id)
    return f"soulmeet-{safe[:80]}"


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


async def _handle_realtime_message(
        message: Dict[str, Any],
        *,
        task: PipelineTask,
        session_id: str,
        components: Any,
) -> None:
    try:
        if message.get("type") == "text_input":
            text = message.get("text", "")
            if text.strip():
                logger.info(f"[{USER_INPUT}] | Task=实时文本输入 | 文本: '{text[:50]}', session={session_id}")
                frame = TranscriptionFrame(
                    text=text,
                    user_id="debug_user",
                    timestamp="",
                    language="zh",
                )
                await task.queue_frame(frame)
        elif message.get("type") == "set_voice_mode":
            enabled = bool(message.get("enabled", True))
            conversation_session_manager.set_voice_reply_enabled(session_id, enabled)
            if components.tts_processor is not None:
                components.tts_processor.set_voice_enabled(enabled)
                logger.info(f"[{USER_INPUT}] | Task=语音模式切换 | 语音回复已{'开启' if enabled else '关闭'}, session={session_id}")
        elif message.get("type") == "set_vad_interrupt":
            enabled = bool(message.get("enabled", True))
            if components.vad_interrupt_strategy is not None:
                components.vad_interrupt_strategy.set_vad_interrupt_enabled(enabled)
            smart_interrupt_gate = getattr(components, "smart_interrupt_gate", None)
            if smart_interrupt_gate is not None:
                smart_interrupt_gate.set_interrupt_enabled(enabled)
            logger.info(
                f"[{USER_INPUT}] | Task=智能语音打断切换 | "
                f"智能打断已{'开启' if enabled else '关闭'}, session={session_id}"
            )
        elif message.get("type") == "interrupt_response":
            await conversation_session_manager.interrupt_session_response(
                session_id,
                reason="user_stop_button",
            )
    except Exception as e:
        logger.error(f"[{USER_INPUT}] | Task=实时文本输入 | 消息解析错误: {e}")


async def _run_bot(
        webrtc_connection: SmallWebRTCConnection,
        session_id: str,
        audience: str,
        system_prompt: str = "",
        conversation_id: str = "",
        user_id: str = "",
        client_ip: str = "",
) -> None:
    """
    为一个 WebRTC 连接创建并运行 Pipeline。

    遵循项目规划:
    - 使用 core/pipeline/factory.py 的 build_pipeline 组装管道
    - Pipeline 组装逻辑在底座，不含人群特有逻辑
    - 事件处理中的问候行为通过回调注入

    Args:
        webrtc_connection: 已初始化的 WebRTC 连接
        session_id:        会话 ID
        audience:          人群标识
        system_prompt:     初始 system prompt
        user_id:           鉴权用户唯一标识（来自 JWT；未登录时为空）
    """
    logger.info(f"[{SESSION_START}] | Task=WebRTC offer接收 | session={session_id}, audience={audience}")

    # 1. 创建 Transport
    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
        ),
    )

    persona = _load_audience_persona(audience)

    # 2. 通过 Pipeline 工厂组装
    components = await build_pipeline(
        transport=transport,
        settings=settings,
        persona=persona,
        system_prompt=system_prompt,
    )

    # 注入 webrtc_connection
    if components.user_text_forward is not None:
        components.user_text_forward.set_connection(webrtc_connection)

    # 3. 创建 PipelineTask
    task = PipelineTask(
        components.pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    conv_session = await conversation_session_manager.get_or_create(
        audience=audience,
        session_id=session_id,
        conversation_id=conversation_id,
        user_id=user_id,
        client_ip=client_ip,
    )
    session_ctx: Optional[SessionContext] = conv_session.session_ctx
    smart_interrupt_gate = getattr(components, "smart_interrupt_gate", None)
    if smart_interrupt_gate is not None:
        async def _smart_interrupt_callback(reason: str, text: str) -> None:
            del text
            await conversation_session_manager.interrupt_session_response(
                session_id,
                reason=f"smart_voice_interrupt:{reason}",
            )

        smart_interrupt_gate.set_interrupt_callback(_smart_interrupt_callback)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        if _on_connected_callback is not None:
            await _on_connected_callback(task, [], persona=persona)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"[{SESSION_END}] | Task=客户端断开 | 客户端断开: session={session_id}")
        current_record = _sessions.get(session_id)
        is_current_connection = (
            current_record is not None
            and current_record.pc_id == webrtc_connection.pc_id
        )
        if is_current_connection:
            current_record.connected = False
            conversation_session_manager.detach_voice_runtime(session_id, webrtc_connection.pc_id)
        await task.cancel()

    @transport.event_handler("on_app_message")
    async def on_app_message(transport, message, sender):
        # message 已被 pipecat SmallWebRTCConnection 解析为 dict，无需再 json.loads
        await _handle_realtime_message(
            message,
            task=task,
            session_id=session_id,
            components=components,
        )

    # 修复：pipecat SmallWebRTCClient.connect() 在连接已建立时提前返回，
    # 不调用 SmallWebRTCConnection.connect()，导致 "connected" 事件无法触发，
    # 音频输入轨道未被设置，语音识别无法接收音频。
    # 在 Pipeline 启动后（所有处理器已处理 StartFrame、transport.setup 已完成），
    # 手动调用 webrtc_connection.connect() 确保 "connected" 事件正确触发。
    @task.event_handler("on_pipeline_started")
    async def on_pipeline_started(pipeline_task, start_frame):
        await webrtc_connection.connect()

    session_ctx.set_user_id(user_id)
    session_ctx.set_conversation_id(conversation_id)
    conversation_session_manager.attach_voice_runtime(
        conv_session,
        connection=webrtc_connection,
        task=task,
        components=components,
        pc_id=webrtc_connection.pc_id,
    )
    _cloned_cfg = get_active_cloned_voice_config(audience)
    if _cloned_cfg:
        components.tts_processor.set_voice(_cloned_cfg["cloned_voice_id"])
        if _cloned_cfg.get("tts_model"):
            components.tts_processor.set_model(_cloned_cfg["tts_model"])
    if components.user_text_forward is not None:
        components.user_text_forward.set_session_ctx(session_ctx)
    if components.soul_companion_processor is not None:
        async def _soul_voice_callback(text: str) -> None:
            await conversation_session_manager.handle_user_text(
                conv_session,
                text,
                timeout_seconds=120.0,
                source="voice",
            )

        components.soul_companion_processor.set_callback(_soul_voice_callback)

    # 6. 记录会话
    _sessions[session_id] = SessionRecord(
        session_id=session_id,
        audience=audience,
        pc_id=webrtc_connection.pc_id,
        task=task,
        components=components,
        session_ctx=session_ctx,
        client_ip=client_ip,
    )

    # 7. 运行 Pipeline
    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)

    # 8. 清理（session / pc / background task）
    conversation_session_manager.detach_voice_runtime(session_id, webrtc_connection.pc_id)
    current_record = _sessions.get(session_id)
    if current_record is not None and current_record.pc_id == webrtc_connection.pc_id:
        del _sessions[session_id]
        if current_record.pc_id in _pcs_map:
            del _pcs_map[current_record.pc_id]
    current_task = asyncio.current_task()
    if _background_tasks.get(session_id) is current_task:
        _background_tasks.pop(session_id, None)
    logger.info(f"[{SESSION_END}] | Task=资源清理 | 会话清理完成: {session_id}")


async def _run_livekit_bot(
        *,
        livekit_url: str,
        agent_token: str,
        room_name: str,
        session_id: str,
        audience: str,
        system_prompt: str = "",
        conversation_id: str = "",
        user_id: str = "",
        client_ip: str = "",
) -> None:
    """为一个 LiveKit 房间创建并运行现有 Qwen STT/LLM/TTS Pipeline。"""
    logger.info(
        f"[{SESSION_START}] | Task=LiveKit房间接入 | session={session_id}, "
        f"room={room_name}, audience={audience}"
    )
    loop = asyncio.get_running_loop()
    transport = LiveKitTransport(
        url=livekit_url,
        token=agent_token,
        room_name=room_name,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
        ),
    )
    livekit_connection = LiveKitDataConnection(transport, loop)

    persona = _load_audience_persona(audience)
    components = await build_pipeline(
        transport=transport,
        settings=settings,
        persona=persona,
        system_prompt=system_prompt,
    )
    if components.user_text_forward is not None:
        components.user_text_forward.set_connection(livekit_connection)

    task = PipelineTask(
        components.pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    conv_session = await conversation_session_manager.get_or_create(
        audience=audience,
        session_id=session_id,
        conversation_id=conversation_id,
        user_id=user_id,
        client_ip=client_ip,
    )
    session_ctx: Optional[SessionContext] = conv_session.session_ctx
    smart_interrupt_gate = getattr(components, "smart_interrupt_gate", None)
    if smart_interrupt_gate is not None:
        async def _smart_interrupt_callback(reason: str, text: str) -> None:
            del text
            await conversation_session_manager.interrupt_session_response(
                session_id,
                reason=f"smart_voice_interrupt:{reason}",
            )

        smart_interrupt_gate.set_interrupt_callback(_smart_interrupt_callback)

    @transport.event_handler("on_connected")
    async def on_connected(transport):
        livekit_connection.refresh_participant_id()
        logger.info(
            f"[{SESSION_START}] | Task=LiveKit已连接 | session={session_id}, "
            f"room={room_name}, agent_participant={livekit_connection.pc_id}"
        )

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant_id):
        logger.info(
            f"[{SESSION_START}] | Task=LiveKit用户入房 | session={session_id}, "
            f"room={room_name}, participant={participant_id}"
        )
        if _on_connected_callback is not None:
            await _on_connected_callback(task, [], persona=persona)

    @transport.event_handler("on_participant_disconnected")
    async def on_participant_disconnected(transport, participant_id):
        logger.info(
            f"[{SESSION_END}] | Task=LiveKit参与者断开 | participant={participant_id}, session={session_id}"
        )
        current_record = _sessions.get(session_id)
        if current_record is not None and current_record.pc_id == livekit_connection.pc_id:
            current_record.connected = False
            conversation_session_manager.detach_voice_runtime(session_id, livekit_connection.pc_id)
        await task.cancel()

    @transport.event_handler("on_data_received")
    async def on_data_received(transport, data: bytes, participant_id: str):
        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception as exc:
            logger.warning(
                f"[{USER_INPUT}] | Task=LiveKit数据消息 | JSON解析失败: "
                f"session={session_id}, participant={participant_id}, error={exc}"
            )
            return
        if isinstance(payload, dict):
            logger.debug(
                f"[{USER_INPUT}] | Task=LiveKit数据消息 | 收到数据消息: "
                f"session={session_id}, participant={participant_id}, payload_type={payload.get('type', '<unknown>')}"
            )
            await _handle_realtime_message(
                payload,
                task=task,
                session_id=session_id,
                components=components,
            )

    session_ctx.set_user_id(user_id)
    session_ctx.set_conversation_id(conversation_id)
    conversation_session_manager.attach_voice_runtime(
        conv_session,
        connection=livekit_connection,
        task=task,
        components=components,
        pc_id=livekit_connection.pc_id,
    )
    _cloned_cfg = get_active_cloned_voice_config(audience)
    if _cloned_cfg:
        components.tts_processor.set_voice(_cloned_cfg["cloned_voice_id"])
        if _cloned_cfg.get("tts_model"):
            components.tts_processor.set_model(_cloned_cfg["tts_model"])
    if components.user_text_forward is not None:
        components.user_text_forward.set_session_ctx(session_ctx)
    if components.soul_companion_processor is not None:
        async def _soul_voice_callback(text: str) -> None:
            await conversation_session_manager.handle_user_text(
                conv_session,
                text,
                timeout_seconds=120.0,
                source="voice",
            )

        components.soul_companion_processor.set_callback(_soul_voice_callback)

    _sessions[session_id] = SessionRecord(
        session_id=session_id,
        audience=audience,
        pc_id=livekit_connection.pc_id,
        task=task,
        components=components,
        session_ctx=session_ctx,
        client_ip=client_ip,
    )

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)

    conversation_session_manager.detach_voice_runtime(session_id, livekit_connection.pc_id)
    current_record = _sessions.get(session_id)
    if current_record is not None and current_record.pc_id == livekit_connection.pc_id:
        del _sessions[session_id]
    current_task = asyncio.current_task()
    if _background_tasks.get(session_id) is current_task:
        _background_tasks.pop(session_id, None)
    logger.info(f"[{SESSION_END}] | Task=LiveKit资源清理 | 会话清理完成: {session_id}")


@router.post("/livekit/token", response_model=LiveKitTokenResponse)
async def create_livekit_token(
        http_request: Request,
        request: LiveKitTokenRequest,
) -> LiveKitTokenResponse:
    requested_session = request.session_id or "<new>"
    logger.info(
        f"[{SESSION_START}] | Task=LiveKitToken请求 | audience={request.audience}, "
        f"session={requested_session}, participant={request.participant_identity or '<auto>'}, "
        f"transport={settings.voice_transport}"
    )
    if settings.voice_transport != "livekit":
        logger.warning(
            f"[{SESSION_START}] | Task=LiveKitToken拒绝 | transport={settings.voice_transport}, "
            f"expected=livekit, session={requested_session}"
        )
        raise HTTPException(status_code=409, detail="Voice transport is not set to livekit")
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
    agent_token = _make_livekit_token(
        identity=f"aini-agent-{session_id[:12]}",
        room_name=room_name,
        name="Aini",
    )

    old_task = _background_tasks.get(session_id)
    if old_task is not None and not old_task.done():
        logger.info(
            f"[{SESSION_END}] | Task=LiveKit旧任务取消 | session={session_id}, "
            f"room={room_name}, old_task_done={old_task.done()}"
        )
        old_task.cancel()

    logger.info(
        f"[{SESSION_START}] | Task=LiveKitToken签发 | session={session_id}, "
        f"room={room_name}, participant={participant_identity}, user_id={user_id or '<空>'}, "
        f"url_configured={'是' if settings.livekit_url else '否'}"
    )
    bg_task = asyncio.create_task(
        _run_livekit_bot(
            livekit_url=settings.livekit_url,
            agent_token=agent_token,
            room_name=room_name,
            session_id=session_id,
            audience=request.audience,
            system_prompt="你是善于情感陪伴。请用简洁的中文回答。",
            conversation_id=conversation_id,
            user_id=user_id,
            client_ip=_extract_client_ip(http_request),
        )
    )

    def _on_task_done(t: asyncio.Task, sid: str = session_id) -> None:
        if _background_tasks.get(sid) is t:
            _background_tasks.pop(sid, None)
        if t.cancelled():
            logger.info(f"[{SESSION_END}] | Task=LiveKit资源清理 | Bot 任务已取消: session={sid}")
        elif t.exception() is not None:
            logger.error(
                f"[{SESSION_END}] | Task=LiveKit资源清理 | Bot 任务失败: session={sid}, error={t.exception()}"
            )

    bg_task.add_done_callback(_on_task_done)
    _background_tasks[session_id] = bg_task
    logger.info(
        f"[{SESSION_START}] | Task=LiveKitAgent启动 | session={session_id}, "
        f"room={room_name}, background_tasks={len(_background_tasks)}"
    )

    return LiveKitTokenResponse(
        url=settings.livekit_url,
        token=frontend_token,
        room_name=room_name,
        session_id=session_id,
        conversation_id=conversation_id,
        participant_identity=participant_identity,
    )


@router.post("/offer", response_model=OfferResponse)
async def handle_offer(
        http_request: Request,
        request: OfferRequest,
) -> OfferResponse:
    """
    处理 WebRTC SDP Offer。

    流程（遵循项目规划 10.4 多人群共存部署）:
    1. 复用或创建 SmallWebRTCConnection
    2. 初始化 SDP（negotiate）
    3. 生成 session_id
    4. 在后台启动 Pipeline（_run_bot）
    5. 返回 SDP answer + session_id + pc_id
    """
    try:
        # 1-2. 复用或创建连接，并初始化 SDP。初始化阶段会显式处理 aioice/aiortc 的 CancelledError。
        webrtc_connection = await _initialize_webrtc_with_retry(request)

        # 3. 生成或复用 session_id。重连时复用旧 session_id，便于 ContextSync 按同一会话恢复上下文。
        if request.session_id:
            try:
                session_id = str(uuid.UUID(request.session_id))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid session_id")
        else:
            session_id = str(uuid.uuid4())

        old_task = _background_tasks.get(session_id)
        if old_task is not None and not old_task.done():
            old_task.cancel()
        old_record = _sessions.pop(session_id, None)
        if old_record is not None:
            _pcs_map.pop(old_record.pc_id, None)

        # 3.5 从 JWT Token 中提取 user_id（无 Token 或无效时 user_id 为空）
        user_id = ""
        token = request.token or ""
        if token:
            try:
                payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
                user_id = payload.get("sub", "")
            except jwt.ExpiredSignatureError:
                logger.warning(f"[{SESSION_START}] | Task=JWT解析 | JWT Token 已过期，user_id 将为空")
            except jwt.InvalidTokenError:
                logger.warning(f"[{SESSION_START}] | Task=JWT解析 | JWT Token 无效，user_id 将为空")

        conversation_id = await _ensure_runtime_conversation_id(
            conversation_id=request.conversation_id or "",
            user_id=user_id,
            audience=request.audience,
            session_id=session_id,
        )

        # 4. 构造 system_prompt（底座提供默认，后续由插件覆盖）
        system_prompt = (
            "你是善于情感陪伴。请用简洁的中文回答。"
        )

        # 5. 后台启动 bot（保存引用防止 GC，添加异常回调防止吞没）
        bg_task = asyncio.create_task(
            _run_bot(
                webrtc_connection=webrtc_connection,
                session_id=session_id,
                audience=request.audience,
                system_prompt=system_prompt,
                conversation_id=conversation_id,
                user_id=user_id,
                client_ip=_extract_client_ip(http_request),
            )
        )

        def _on_task_done(t: asyncio.Task, sid: str = session_id) -> None:
            if _background_tasks.get(sid) is t:
                _background_tasks.pop(sid, None)
            if t.cancelled():
                logger.info(f"[{SESSION_END}] | Task=资源清理 | Bot 任务已取消: session={sid}")
            elif t.exception() is not None:
                logger.error(
                    f"[{SESSION_END}] | Task=资源清理 | Bot 任务失败: session={sid}, error={t.exception()}"
                )
                # 确保异常情况下也清理资源（正常路径在 _run_bot 步骤 8 清理）
                session = _sessions.get(sid)
                if session is not None and session.pc_id == webrtc_connection.pc_id:
                    _sessions.pop(sid, None)
                    _pcs_map.pop(session.pc_id, None)

        bg_task.add_done_callback(_on_task_done)
        _background_tasks[session_id] = bg_task

        # 6. 返回 SDP answer
        return OfferResponse(
            sdp=webrtc_connection.pc.localDescription.sdp,
            type=webrtc_connection.pc.localDescription.type,
            pc_id=webrtc_connection.pc_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

    except HTTPException:
        raise
    except asyncio.CancelledError as e:
        logger.warning(f"[{SESSION_START}] | Task=WebRTC offer接收 | 处理 offer 被取消: {e}")
        raise HTTPException(status_code=503, detail="WebRTC offer was cancelled, please retry")
    except Exception as e:
        logger.error(f"[{SESSION_START}] | Task=WebRTC offer接收 | 处理 offer 失败: {e}")
        raise HTTPException(status_code=500, detail=f"WebRTC offer failed: {e}")


@router.get("/status/{session_id}", response_model=StatusResponse)
async def get_session_status(session_id: str) -> StatusResponse:
    """查询会话连接状态。"""
    if session_id not in _sessions:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found"
        )

    session = _sessions[session_id]
    uptime = time.time() - session.created_at

    current_node = "active_listening"

    return StatusResponse(
        session_id=session.session_id,
        audience=session.audience,
        current_node=current_node,
        connected=session.connected,
        uptime_seconds=round(uptime, 1),
    )


def get_active_sessions() -> Dict[str, SessionRecord]:
    """供 session.py 路由查询活跃会话（进程内共享）。"""
    return _sessions
