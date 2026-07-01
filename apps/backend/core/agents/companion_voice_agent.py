"""LiveKit Agents worker for realtime companion voice."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, AsyncIterable, Dict, List, Mapping, Optional
from uuid import uuid4

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomInputOptions,
    RoomOutputOptions,
    WorkerOptions,
    cli,
    inference,
)
from livekit.agents import llm
from livekit.plugins import aliyun
from loguru import logger

from core.config import settings
from core.logging_utils import AI_REPLY, SESSION_END, SESSION_START, TTS, USER_INPUT
from core.soul_companion.default_location import default_location_service
from core.soul_companion.runtime import answer_user_text

_VOICE_BROADCAST_REFERENCE_RE = re.compile(
    r"(?:^|\n)\s*(?:参考链接|References?)\s*[:：]?[\s\S]*$",
    re.IGNORECASE,
)
_VOICE_BROADCAST_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_VOICE_BROADCAST_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_VOICE_BROADCAST_IMAGE_RE = re.compile(r"!\[([^\]]*)]\([^)]+\)")
_VOICE_BROADCAST_LINK_RE = re.compile(r"\[([^\]]+)]\([^)]+\)")
_VOICE_BROADCAST_BARE_URL_RE = re.compile(r"https?://\S+")


def _normalize_voice_broadcast_text(raw: str) -> str:
    text = _VOICE_BROADCAST_REFERENCE_RE.sub(" ", raw)
    text = _VOICE_BROADCAST_CODE_BLOCK_RE.sub(" ", text)
    text = _VOICE_BROADCAST_INLINE_CODE_RE.sub(r"\1", text)
    text = _VOICE_BROADCAST_IMAGE_RE.sub(r"\1", text)
    text = _VOICE_BROADCAST_LINK_RE.sub(r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = _VOICE_BROADCAST_BARE_URL_RE.sub(" ", text)
    text = re.sub(r"[|*_>#]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class RoomDataPublisher:
    def __init__(self, room: rtc.Room) -> None:
        self._room = room

    async def send_app_message(self, payload: Mapping[str, Any]) -> None:
        try:
            data = json.dumps(dict(payload), ensure_ascii=False)
            await self._room.local_participant.publish_data(data, reliable=True)
        except Exception as exc:
            logger.warning(
                f"[{AI_REPLY}] | Task=LiveKitAgent数据发送 | 发送失败: "
                f"type={payload.get('type')}, error={exc}"
            )


class VoiceBroadcastBridge:
    """Streams text-runtime deltas into LiveKit TTS without involving the LLM."""

    def __init__(self, session: AgentSession) -> None:
        self._session = session
        self._message_id = ""
        self._queue: Optional[asyncio.Queue[Optional[str]]] = None
        self._task: Optional[asyncio.Task[None]] = None
        self._chunk_count = 0
        self._char_count = 0
        self._started_at = 0.0

    async def start(self, message_id: str) -> None:
        if self._message_id and self._message_id != message_id:
            await self.cancel("new_message")
        elif self._task and not self._task.done():
            return

        self._message_id = message_id
        self._queue = asyncio.Queue()
        self._chunk_count = 0
        self._char_count = 0
        self._started_at = time.perf_counter()
        self._task = asyncio.create_task(self._run(message_id, self._queue))
        logger.info(
            f"[{TTS}] | Task=LiveKit聊天播报 | start message_id={message_id[:8]}"
        )

    async def append(self, message_id: str, text: str) -> None:
        speech_text = _normalize_voice_broadcast_text(text)
        if not speech_text:
            return
        if not self._queue or self._message_id != message_id:
            await self.start(message_id)
        queue = self._queue
        if queue is None:
            return
        self._chunk_count += 1
        self._char_count += len(speech_text)
        if self._chunk_count == 1:
            elapsed_ms = int((time.perf_counter() - self._started_at) * 1000)
            logger.info(
                f"[{TTS}] | Task=LiveKit聊天播报 | first_delta "
                f"message_id={message_id[:8]}, elapsed_ms={elapsed_ms}, chars={len(speech_text)}"
            )
        await queue.put(speech_text)

    async def finish(self, message_id: str, final_text: str = "") -> None:
        if final_text and (not self._queue or self._message_id != message_id or self._chunk_count == 0):
            await self.append(message_id, final_text)
        if not self._queue or self._message_id != message_id:
            return
        await self._queue.put(None)
        logger.info(
            f"[{TTS}] | Task=LiveKit聊天播报 | finish message_id={message_id[:8]}, "
            f"chunks={self._chunk_count}, chars={self._char_count}"
        )

    async def cancel(self, reason: str = "cancel") -> None:
        if self._queue is not None:
            await self._queue.put(None)
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._message_id:
            logger.info(
                f"[{TTS}] | Task=LiveKit聊天播报 | cancel "
                f"message_id={self._message_id[:8]}, reason={reason}"
            )
        self._message_id = ""
        self._queue = None
        self._task = None
        self._chunk_count = 0
        self._char_count = 0
        self._started_at = 0.0

    async def _run(self, message_id: str, queue: asyncio.Queue[Optional[str]]) -> None:
        async def text_stream() -> AsyncIterable[str]:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk

        try:
            handle = self._session.say(
                text_stream(),
                allow_interruptions=True,
                add_to_chat_ctx=False,
            )
            await handle.wait_for_playout()
            elapsed_ms = int((time.perf_counter() - self._started_at) * 1000)
            logger.info(
                f"[{TTS}] | Task=LiveKit聊天播报 | playout_done "
                f"message_id={message_id[:8]}, elapsed_ms={elapsed_ms}"
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                f"[{TTS}] | Task=LiveKit聊天播报 | 播放失败 "
                f"message_id={message_id[:8]}, error={exc}"
            )
        finally:
            if self._message_id == message_id:
                self._message_id = ""
                self._queue = None
                self._task = None


def _metadata_from_job(ctx: JobContext) -> Dict[str, str]:
    raw = getattr(ctx.job, "metadata", "") or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"[{SESSION_START}] | Task=LiveKitAgent元数据 | JSON解析失败: {raw[:120]}")
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {str(k): str(v or "") for k, v in payload.items()}


def _latest_user_text(chat_ctx: llm.ChatContext) -> str:
    for message in reversed(chat_ctx.messages()):
        if message.role != "user":
            continue
        text = (message.text_content or "").strip()
        if text:
            return text
    return ""


def _recent_chat_messages(chat_ctx: llm.ChatContext) -> List[Dict[str, str]]:
    mapped: List[Dict[str, str]] = []
    for message in chat_ctx.messages()[-12:]:
        if message.role not in ("user", "assistant"):
            continue
        text = (message.text_content or "").strip()
        if text:
            mapped.append({"role": message.role, "content": text})
    return mapped


class CompanionVoiceAgent(Agent):
    def __init__(
        self,
        *,
        metadata: Mapping[str, str],
        publisher: RoomDataPublisher,
    ) -> None:
        self._metadata = metadata
        self._publisher = publisher
        super().__init__(
            instructions=(
                "你是一个稳定、温柔、低延迟的情感陪伴语音机器人。"
                "用自然、简洁的中文回应用户。"
                "当用户提出查询、计划、提醒、天气、健康或出行等任务时，主动完成任务并给出清晰结果。"
                "实时语音场景下不要长篇铺陈，优先短句、可被打断、可继续追问。"
            ),
        )

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: Any,
    ) -> AsyncIterable[str]:
        del tools, model_settings
        user_text = _latest_user_text(chat_ctx)
        if not user_text:
            return

        session_id = self._metadata.get("session_id", "")
        conversation_id = self._metadata.get("conversation_id", "")
        audience = self._metadata.get("audience", settings.audience)
        user_id = self._metadata.get("user_id", "")
        client_ip = self._metadata.get("client_ip", "")
        message_id = str(uuid4())
        block_id = "main"
        chunk_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        streamed_chunks: List[str] = []

        async def publish(payload: Mapping[str, Any]) -> None:
            await self._publisher.send_app_message(payload)

        async def progress_callback(payload: Dict[str, Any]) -> None:
            await publish(payload)

        async def stream_callback(chunk: str) -> None:
            if not chunk:
                return
            streamed_chunks.append(chunk)
            await publish({
                "type": "content_block_delta",
                "message_id": message_id,
                "block_id": block_id,
                "delta": chunk,
            })
            await chunk_queue.put(chunk)

        await publish({
            "type": "assistant_message_start",
            "message_id": message_id,
            "source": "voice_agent",
        })
        await publish({
            "type": "content_block_start",
            "message_id": message_id,
            "block_id": block_id,
            "block_type": "markdown",
            "source": "voice_agent",
        })

        default_location = await default_location_service.resolve(
            session_id=session_id,
            user_id=user_id,
            client_ip=client_ip,
        )
        default_location_context = {
            **default_location.to_prompt_context(),
            "session_id": session_id,
            "user_id": user_id,
            "client_ip": client_ip,
        }
        answer_task = asyncio.create_task(
            answer_user_text(
                user_text,
                recent_messages=_recent_chat_messages(chat_ctx),
                allow_agent=True,
                progress_callback=progress_callback,
                stream_callback=stream_callback,
                reminder_context={
                    "session_id": session_id,
                    "conversation_id": conversation_id,
                    "audience": audience,
                    "user_id": user_id,
                    "client_ip": client_ip,
                    "source_text": user_text,
                },
                default_location_context=default_location_context,
            )
        )
        try:
            while not answer_task.done() or not chunk_queue.empty():
                try:
                    chunk = await asyncio.wait_for(chunk_queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                if chunk:
                    yield chunk

            result = await answer_task
            final_text = str(result.text or "").strip()
            if final_text and not streamed_chunks:
                await publish({
                    "type": "content_block_delta",
                    "message_id": message_id,
                    "block_id": block_id,
                    "delta": final_text,
                })
                yield final_text

            await publish({
                "type": "content_block_finish",
                "message_id": message_id,
                "block_id": block_id,
            })
            finish_payload: Dict[str, Any] = {
                "type": "assistant_message_finish",
                "message_id": message_id,
                "text": final_text,
                "source": result.source,
            }
            if result.artifact:
                finish_payload["artifact"] = result.artifact
            await publish(finish_payload)
            logger.info(
                f"[{AI_REPLY}] | Task=LiveKitAgent回复 | session={session_id[:8]}, "
                f"source={result.source}, text='{final_text[:80]}'"
            )
        except asyncio.CancelledError:
            answer_task.cancel()
            await publish({"type": "assistant_text_interrupted", "reason": "voice_interruption"})
            logger.info(
                f"[{AI_REPLY}] | Task=LiveKitAgent打断 | session={session_id[:8]}, text='{user_text[:80]}'"
            )
            raise
        except Exception as exc:
            answer_task.cancel()
            fallback = "我这边语音思考暂时卡住了，你可以再说一遍。"
            await publish({
                "type": "assistant_message_finish",
                "message_id": message_id,
                "text": fallback,
                "source": "voice_agent:error",
            })
            logger.error(
                f"[{AI_REPLY}] | Task=LiveKitAgent回复 | 失败: session={session_id[:8]}, error={exc}"
            )
            yield fallback


def _build_agent_session() -> AgentSession:
    tts_voice = settings.voice_agent_tts_voice or settings.dashscope_tts_voice

    return AgentSession(
        stt=aliyun.STT(
            model=settings.voice_agent_stt_model,
            language=settings.voice_agent_stt_language,
            api_key=settings.dashscope_api_key,
        ),
        vad=inference.VAD(
            model="silero",
            activation_threshold=settings.voice_agent_vad_activation_threshold,
        ),
        tts=aliyun.TTS(
            api_key=settings.dashscope_api_key,
            model=settings.voice_agent_tts_model,
            voice=tts_voice,
            sample_rate=24000,
        ),
        turn_handling={
            "turn_detection": inference.TurnDetector(
                version=settings.voice_agent_turn_detector_version,
                api_key=settings.livekit_api_key,
                api_secret=settings.livekit_api_secret,
            ),
            "endpointing": {
                "mode": settings.voice_agent_endpointing_mode,
                "min_delay": settings.voice_agent_min_endpointing_delay,
                "max_delay": settings.voice_agent_max_endpointing_delay,
                "alpha": settings.voice_agent_endpointing_alpha,
            },
            "interruption": {
                "enabled": True,
                "mode": "adaptive",
                "min_duration": settings.voice_agent_min_interruption_duration,
                "min_words": settings.voice_agent_min_interruption_words,
                "resume_false_interruption": True,
                "false_interruption_timeout": settings.voice_agent_false_interruption_timeout,
                "backchannel_boundary": (
                    settings.voice_agent_backchannel_min_seconds,
                    settings.voice_agent_backchannel_max_seconds,
                ),
            },
            "preemptive_generation": {
                "enabled": settings.voice_agent_preemptive_generation_enabled,
                "preemptive_tts": settings.voice_agent_preemptive_tts_enabled,
            },
        },
        user_away_timeout=None,
    )


async def entrypoint(ctx: JobContext) -> None:
    metadata = _metadata_from_job(ctx)
    session_id = metadata.get("session_id", "")
    room_name = getattr(ctx.room, "name", "")
    logger.info(
        f"[{SESSION_START}] | Task=LiveKitAgent启动 | "
        f"room={room_name}, session={session_id or '<empty>'}, agent={settings.voice_agent_name}"
    )
    publisher = RoomDataPublisher(ctx.room)
    session = _build_agent_session()
    voice_broadcast = VoiceBroadcastBridge(session)

    @session.on("user_input_transcribed")
    def _on_user_input_transcribed(event: Any) -> None:
        text = str(getattr(event, "transcript", "") or "").strip()
        if not text:
            return
        event_type = "user_text" if bool(getattr(event, "is_final", False)) else "user_text_partial"
        logger.debug(
            f"[{USER_INPUT}] | Task=LiveKitAgent转写 | session={session_id[:8]}, "
            f"final={event_type == 'user_text'}, text='{text[:80]}'"
        )
        asyncio.create_task(publisher.send_app_message({"type": event_type, "text": text}))

    @session.on("agent_state_changed")
    def _on_agent_state_changed(event: Any) -> None:
        asyncio.create_task(
            publisher.send_app_message({
                "type": "agent_state",
                "old_state": getattr(event, "old_state", ""),
                "new_state": getattr(event, "new_state", ""),
            })
        )

    @session.on("user_state_changed")
    def _on_user_state_changed(event: Any) -> None:
        asyncio.create_task(
            publisher.send_app_message({
                "type": "user_state",
                "old_state": getattr(event, "old_state", ""),
                "new_state": getattr(event, "new_state", ""),
            })
        )

    @session.on("agent_false_interruption")
    def _on_false_interruption(event: Any) -> None:
        asyncio.create_task(
            publisher.send_app_message({
                "type": "agent_false_interruption",
                "resumed": bool(getattr(event, "resumed", False)),
            })
        )

    def _on_data_received(packet: Any) -> None:
        try:
            raw = getattr(packet, "data", b"")
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw))
        except Exception as exc:
            logger.warning(f"[{USER_INPUT}] | Task=LiveKitAgent数据消息 | 解析失败: {exc}")
            return
        if not isinstance(payload, dict):
            return
        payload_type = str(payload.get("type") or "")
        if payload_type == "interrupt_response":
            asyncio.ensure_future(voice_broadcast.cancel("interrupt_response"))
            asyncio.ensure_future(session.interrupt(force=True))
            return

        if payload_type == "voice_broadcast_cancel":
            asyncio.ensure_future(voice_broadcast.cancel(str(payload.get("reason") or "client_cancel")))
            return

        if payload_type == "voice_broadcast_start":
            message_id = str(payload.get("message_id") or uuid4())
            asyncio.ensure_future(voice_broadcast.start(message_id))
            return

        if payload_type == "voice_broadcast_delta":
            message_id = str(payload.get("message_id") or "")
            text = str(payload.get("text") or payload.get("delta") or "")
            if message_id and text:
                asyncio.ensure_future(voice_broadcast.append(message_id, text))
            return

        if payload_type == "voice_broadcast_finish":
            message_id = str(payload.get("message_id") or "")
            final_text = str(payload.get("text") or "")
            if message_id:
                asyncio.ensure_future(voice_broadcast.finish(message_id, final_text))

    ctx.room.on("data_received", _on_data_received)

    disconnected: asyncio.Future[None] = asyncio.Future()

    def _on_disconnected(*_: Any) -> None:
        if not disconnected.done():
            disconnected.set_result(None)

    ctx.room.on("disconnected", _on_disconnected)

    async def _shutdown(_: str = "") -> None:
        if not disconnected.done():
            disconnected.set_result(None)

    ctx.add_shutdown_callback(_shutdown)

    await session.start(
        agent=CompanionVoiceAgent(metadata=metadata, publisher=publisher),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            audio_enabled=True,
            text_enabled=True,
            audio_sample_rate=16000,
            audio_num_channels=1,
        ),
        room_output_options=RoomOutputOptions(
            audio_enabled=True,
            transcription_enabled=True,
            audio_sample_rate=24000,
            audio_num_channels=1,
        ),
        record=False,
    )
    if settings.voice_agent_greeting_enabled:
        await session.say("我在，你可以直接和我说。", allow_interruptions=True)

    await disconnected
    await voice_broadcast.cancel("session_disconnected")
    await session.aclose()
    logger.info(
        f"[{SESSION_END}] | Task=LiveKitAgent结束 | room={room_name}, session={session_id or '<empty>'}"
    )


def run_worker() -> None:
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=settings.voice_agent_name,
            ws_url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
    )


if __name__ == "__main__":
    run_worker()
