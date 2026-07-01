"""Soul companion conversation runtime shared by text and voice inputs."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException
from loguru import logger

from core.conversation.context_manager import AsyncContextManager
from core.conversation.history import HistoryManager
from core.conversation.public_artifact import public_artifact
from core.conversation.store import ConversationStore
from core.emotion.signal_detector import SignalDetector
from core.logging_utils import (
    AI_REPLY,
    MEM_SYS,
    SESSION_END,
    SESSION_START,
    STARTUP,
    TTS,
    USER_INPUT,
    flatten_content,
)
from core.observability import get_trace_recorder
from core.soul_companion import answer_user_text
from core.soul_companion.default_location import default_location_service
from core.soul_companion.reminders import (
    ReminderJob,
    reminder_due_text,
    reminder_scheduler,
)
from core.tools.primitives.http_fetch import HttpFetch
from core.tools.primitives.kv_store import KVStore
from core.tools.primitives.timer import TimerManager
from core.tools.registry import ToolRegistry

TEXT_STREAM_CHUNK_MIN_CHARS = 48
TEXT_STREAM_CHUNK_MAX_CHARS = 96
TEXT_STREAM_CHUNK_DELAY_SECONDS = 0.035
STREAM_DELTA_MIN_CHARS = 12
STREAM_DELTA_MAX_CHARS = 48
STREAM_DELTA_MAX_DELAY_SECONDS = 0.06
STREAM_DELTA_BREAK_CHARS = "。！？；;：:\n"
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]{1,160})\]\((https?://[^\s)]+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s<>\])）\"'，。；;、]+")
_REFERENCE_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(?:(?:第\s*)?(?:[一二三四五六七八九十百\d]+)\s*[、.．)：:]\s*)?(?:\*\*)?\s*(?:参考链接|参考资料|参考来源|参考网页|参考文献|引用链接|引用来源|资料来源|来源链接|信息来源)\s*(?:\*\*)?\s*(?:[：:].*)?$"
)


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reference_label_for_url(url: str) -> str:
    host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", url, flags=re.IGNORECASE).split("/", 1)[0])
    known = {
        "gov.cn": "中国政府网",
        "www.gov.cn": "中国政府网",
        "cctv.com": "央视网",
        "news.cctv.com": "央视网",
        "nhsa.gov.cn": "国家医保局",
        "www.nhsa.gov.cn": "国家医保局",
        "12306.cn": "12306",
        "kyfw.12306.cn": "12306",
    }
    return known.get(host, host or "参考链接")


def _append_reference(references: List[Tuple[str, str]], seen: set[str], label: str, url: str) -> None:
    clean_url = url.strip().rstrip(".,，。；;、")
    if not clean_url or clean_url in seen:
        return
    seen.add(clean_url)
    references.append((label.strip() or _reference_label_for_url(clean_url), clean_url))


def _artifact_has_web_references(artifact: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(artifact, dict):
        return False
    source_text = " ".join(
        str(item)
        for item in (
            artifact.get("tool"),
            artifact.get("source"),
            ",".join(str(tool) for tool in artifact.get("tools_used", []) if tool)
            if isinstance(artifact.get("tools_used"), list)
            else "",
        )
        if item
    )
    return "web_search" in source_text or "web_extract" in source_text


def _collect_artifact_references(
    value: Any,
    references: List[Tuple[str, str]],
    seen: set[str],
    *,
    depth: int = 0,
) -> None:
    if depth > 8 or len(references) >= 8:
        return
    if isinstance(value, list):
        for item in value:
            _collect_artifact_references(item, references, seen, depth=depth + 1)
            if len(references) >= 8:
                return
        return
    if not isinstance(value, dict):
        return

    raw_url = value.get("url")
    if isinstance(raw_url, str) and raw_url.startswith(("http://", "https://")):
        label = ""
        for key in ("title", "name", "label", "source"):
            raw_label = value.get(key)
            if isinstance(raw_label, str) and raw_label.strip():
                label = raw_label.strip()
                break
        _append_reference(references, seen, label or _reference_label_for_url(raw_url), raw_url)

    for key, child in value.items():
        if key.lower() in {"content", "text", "description", "markdown"}:
            continue
        if isinstance(child, (dict, list)):
            _collect_artifact_references(child, references, seen, depth=depth + 1)
            if len(references) >= 8:
                return


def _normalize_reply_number_markers(text: str) -> str:
    """Turn keycap-number emoji list markers into plain numeric markers."""
    if not text:
        return text
    normalized = re.sub(r"(?m)^(\s*)([0-9])\ufe0f?\u20e3\s*", r"\1\2. ", text)
    normalized = re.sub(r"([0-9])\ufe0f?\u20e3", r"\1", normalized)
    return normalized.replace("🔟", "10")


def _strip_disallowed_reply_emoji(text: str) -> str:
    if not text:
        return text
    return text.translate(str.maketrans("", "", "😊🧓👵👴"))


def _move_reply_urls_to_references(text: str, artifact: Optional[Dict[str, Any]] = None) -> str:
    if not text:
        return text

    references: List[Tuple[str, str]] = []
    seen: set[str] = set()

    body = text
    if "http://" in text or "https://" in text:
        def replace_markdown_link(match: re.Match[str]) -> str:
            label = match.group(1).strip()
            url = match.group(2).strip()
            _append_reference(references, seen, label, url)
            return label

        body = _MARKDOWN_LINK_RE.sub(replace_markdown_link, body)

        def replace_bare_url(match: re.Match[str]) -> str:
            url = match.group(0).strip()
            _append_reference(references, seen, _reference_label_for_url(url), url)
            return ""

        body = _BARE_URL_RE.sub(replace_bare_url, body)
        body = re.sub(r"\s+([，。；;、])", r"\1", body)
        body = re.sub(r"(?m)[ \t]+$", "", body)
        body = re.sub(
            r"(?m)^([（(]?\s*(?:来源|参考|链接|URL|网址)[：:])\s*([）)]?)\s*$",
            lambda match: f"{match.group(1)} 见文末参考链接{match.group(2)}",
            body,
        )
        body = re.sub(r"\n{3,}", "\n\n", body).strip()

    if _artifact_has_web_references(artifact):
        _collect_artifact_references(artifact, references, seen)

    if not references:
        return body

    body = _strip_existing_reference_section(body)

    reference_lines = ["**参考链接：**"]
    for label, url in references:
        safe_label = label.replace("[", "").replace("]", "").strip() or _reference_label_for_url(url)
        reference_lines.append(f"- [{safe_label}]({url})")
    references_text = "\n".join(reference_lines)
    return f"{body}\n\n{references_text}" if body else references_text


def _strip_existing_reference_section(text: str) -> str:
    """Remove model-written reference sections before appending normalized links."""
    if not text:
        return text

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _REFERENCE_HEADING_RE.match(line.strip()):
            return "\n".join(lines[:index]).strip()
    return text.strip()


def _normalize_assistant_reply_text(text: str, artifact: Optional[Dict[str, Any]] = None) -> str:
    return _move_reply_urls_to_references(
        _strip_disallowed_reply_emoji(_normalize_reply_number_markers(text)),
        artifact=artifact,
    )


def _iter_text_stream_chunks(text: str) -> List[str]:
    chunks: List[str] = []
    buffer = ""
    for char in text:
        buffer += char
        should_flush = (
            len(buffer) >= TEXT_STREAM_CHUNK_MAX_CHARS
            or (
                len(buffer) >= TEXT_STREAM_CHUNK_MIN_CHARS
                and char in "。！？；;：:\n"
            )
        )
        if should_flush:
            chunks.append(buffer)
            buffer = ""
    if buffer:
        chunks.append(buffer)
    return chunks


class SessionContext:
    """Per-session storage and memory context for the Soul runtime."""

    def __init__(
        self,
        audience: str,
        session_id: str,
        store: ConversationStore,
        history_manager: HistoryManager,
        signal_detector: SignalDetector,
        tool_registry: ToolRegistry,
        http_fetch: HttpFetch,
        timer_manager: TimerManager,
        kv_store: KVStore,
        context_manager: Optional[AsyncContextManager] = None,
        speaker_id: str = "",
        context_config: Optional[Dict[str, Any]] = None,
        task_packer: Optional[Any] = None,
        zmq_client: Optional[Any] = None,
        conversation_id: str = "",
    ) -> None:
        del task_packer, zmq_client
        self._audience = audience
        self._session_id = session_id
        self._store = store
        self._history = history_manager
        self._signal_detector = signal_detector
        self._tool_registry = tool_registry
        self._http_fetch = http_fetch
        self._timer_manager = timer_manager
        self._kv_store = kv_store
        self._context_manager = context_manager
        self._speaker_id = speaker_id or session_id
        self._context_config = context_config
        self._user_id = ""
        self._conversation_id = conversation_id
        self._artifacts: List[Dict[str, Any]] = []
        logger.info(
            f"[{STARTUP}] | Task=Soul会话上下文 | 创建: "
            f"audience='{audience}', session='{session_id}', speaker='{self._speaker_id}'"
        )

    @property
    def namespace(self) -> str:
        return f"{self._audience}:{self._session_id}"

    @property
    def audience(self) -> str:
        return self._audience

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def speaker_id(self) -> str:
        return self._speaker_id

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def conversation_id(self) -> str:
        return self._conversation_id

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    @property
    def has_active_tasks(self) -> bool:
        return False

    def set_user_id(self, user_id: str) -> None:
        self._user_id = user_id or ""

    def set_conversation_id(self, conversation_id: str) -> None:
        self._conversation_id = conversation_id or ""

    async def add_message(
        self,
        role: str,
        content: str,
        *,
        source: str = "",
        artifact: Optional[Dict[str, Any]] = None,
    ) -> None:
        await self._store.append_message(
            key=self.namespace,
            role=role,
            content=content,
        )
        if self._context_manager is None:
            logger.debug(f"[{MEM_SYS}] | Task=Soul消息写入 | context_manager 未配置, ns={self.namespace}")
            return
        await self._context_manager.on_message(
            namespace=self.namespace,
            session_id=self._session_id,
            speaker_id=self._speaker_id,
            audience=self._audience,
            role=role,
            content=content,
            source=source,
            artifact=artifact,
            context_config=self._context_config,
            user_id=self._user_id,
            conversation_id=self._conversation_id,
        )

    async def get_recent_messages(self, n: int) -> List[Dict[str, str]]:
        return await self._history.get_recent(key=self.namespace, n=n)

    async def get_message_count(self) -> int:
        return await self._store.get_message_count(self.namespace)

    async def get_messages(self, limit: int = 50) -> List[Dict[str, str]]:
        messages = await self._store.get_messages(self.namespace)
        return messages[-limit:] if limit > 0 else messages

    def remember_task_artifact(self, artifact: Optional[Dict[str, Any]]) -> None:
        if isinstance(artifact, dict):
            self._artifacts.append(artifact)
            self._artifacts = self._artifacts[-8:]

    def has_task_context_for_routing(self) -> bool:
        return False

    async def on_session_end(self) -> None:
        return None


class ConversationSession:
    """Single business conversation shared by HTTP text and realtime voice."""

    def __init__(
        self,
        *,
        session_id: str,
        audience: str,
        session_ctx: SessionContext,
        conversation_id: str = "",
        user_id: str = "",
        client_ip: str = "",
    ) -> None:
        self.session_id = session_id
        self.audience = audience
        self.session_ctx = session_ctx
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.client_ip = client_ip
        self.pending_http_replies: List[asyncio.Future] = []
        self.active_response_task: Optional[asyncio.Task] = None
        self.background_response_tasks = set()
        self.text_progress_subscribers: List[asyncio.Queue] = []
        self.text_event_history: List[Dict[str, Any]] = []
        self.text_event_seq = 0
        self.voice_reply_enabled = False
        self.voice_connection: Any = None
        self.voice_task: Any = None
        self.voice_components: Any = None
        self.voice_pc_id = ""
        self.recent_messages: List[Dict[str, str]] = []
        self.message_count = 0
        self._lock = asyncio.Lock()

    @property
    def has_voice_runtime(self) -> bool:
        return self.voice_connection is not None and self.voice_task is not None

    @property
    def has_active_tasks(self) -> bool:
        return False

    def record_message(self, role: str, content: str) -> None:
        self.recent_messages.append({"role": role, "content": content})
        self.recent_messages = self.recent_messages[-100:]
        self.message_count += 1

    def remember_task_artifact(self, artifact: Optional[Dict[str, Any]]) -> None:
        self.session_ctx.remember_task_artifact(artifact)

    def add_text_progress_subscriber(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        self.text_progress_subscribers.append(queue)
        return queue

    def remove_text_progress_subscriber(self, queue: asyncio.Queue) -> None:
        try:
            self.text_progress_subscribers.remove(queue)
        except ValueError:
            pass

    async def publish_text_event(self, payload: Dict[str, Any]) -> None:
        self.text_event_seq += 1
        payload = dict(payload)
        payload["_seq"] = self.text_event_seq
        self.text_event_history.append(payload)
        self.text_event_history = self.text_event_history[-300:]

        stale: List[asyncio.Queue] = []
        for queue in list(self.text_progress_subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    stale.append(queue)
        for queue in stale:
            self.remove_text_progress_subscriber(queue)


class ConversationSessionManager:
    def __init__(self) -> None:
        self._session_factory: Optional[Callable[[str, str], SessionContext]] = None
        self._sessions: Dict[str, ConversationSession] = {}
        self._retired_session_ids: set[str] = set()

    def configure(
        self,
        *,
        session_factory: Callable[[str, str], SessionContext],
        result_handler: Any = None,
    ) -> None:
        del result_handler
        self._session_factory = session_factory
        logger.info(f"[{SESSION_START}] | Task=Soul会话配置 | session_factory=已配置")

    def get(self, session_id: str) -> Optional[ConversationSession]:
        return self._sessions.get(session_id)

    async def start_reminder_scheduler(self) -> None:
        await reminder_scheduler.start(self._deliver_reminder_job)

    async def stop_reminder_scheduler(self) -> None:
        await reminder_scheduler.stop()

    async def get_or_create(
        self,
        *,
        audience: str,
        session_id: Optional[str] = None,
        conversation_id: str = "",
        user_id: str = "",
        client_ip: str = "",
    ) -> ConversationSession:
        if self._session_factory is None:
            raise HTTPException(status_code=503, detail="Conversation runtime is not initialized")

        requested_session_id = session_id
        if requested_session_id and requested_session_id in self._retired_session_ids:
            logger.info(
                f"[{SESSION_START}] | Task=Soul会话创建 | session={requested_session_id[:8]}, "
                f"reason=retired_session_id, action=allocate_new"
            )
            session_id = None

        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            if user_id and user_id != session.user_id:
                session.user_id = user_id
                session.session_ctx.set_user_id(user_id)
            if conversation_id and conversation_id != session.conversation_id:
                session.conversation_id = conversation_id
                session.session_ctx.set_conversation_id(conversation_id)
            if client_ip:
                session.client_ip = client_ip
            return session

        new_session_id = session_id or str(uuid4())
        session_ctx = self._session_factory(audience, new_session_id)
        session_ctx.set_user_id(user_id)
        session_ctx.set_conversation_id(conversation_id)
        session = ConversationSession(
            session_id=new_session_id,
            audience=audience,
            session_ctx=session_ctx,
            conversation_id=conversation_id,
            user_id=user_id,
            client_ip=client_ip,
        )
        self._sessions[new_session_id] = session
        logger.info(
            f"[{SESSION_START}] | Task=Soul会话创建 | session={new_session_id[:8]}, "
            f"audience={audience}, user_id={'已绑定' if user_id else '<空>'}, "
            f"client_ip={client_ip or '<空>'}, active_sessions={len(self._sessions)}"
        )
        return session

    def retire_session_id(self, session_id: str) -> None:
        if session_id:
            self._retired_session_ids.add(session_id)
            logger.info(f"[{SESSION_END}] | Task=Soul会话退休 | session={session_id[:8]}")

    def attach_voice_runtime(
        self,
        session: ConversationSession,
        *,
        connection: Any,
        task: Any,
        components: Any,
        pc_id: str,
    ) -> None:
        session.voice_connection = connection
        session.voice_task = task
        session.voice_components = components
        session.voice_pc_id = pc_id
        logger.info(
            f"[{SESSION_START}] | Task=语音Runtime挂载 | session={session.session_id[:8]}, "
            f"pc_id={pc_id}, voice_reply={session.voice_reply_enabled}"
        )

    def detach_voice_runtime(self, session_id: str, pc_id: str = "") -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        if pc_id and session.voice_pc_id and session.voice_pc_id != pc_id:
            logger.warning(
                f"[{SESSION_END}] | Task=语音Runtime解绑跳过 | session={session_id[:8]}, "
                f"request_pc={pc_id}, active_pc={session.voice_pc_id}"
            )
            return
        session.voice_connection = None
        session.voice_task = None
        session.voice_components = None
        session.voice_pc_id = ""
        logger.info(f"[{SESSION_END}] | Task=语音Runtime解绑 | session={session_id[:8]}")

    def set_voice_reply_enabled(self, session_id: str, enabled: bool) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            logger.warning(
                f"[{USER_INPUT}] | Task=语音播报开关 | session={session_id[:8]}, "
                f"enabled={enabled}, reason=session_not_found"
            )
            return
        session.voice_reply_enabled = enabled
        logger.info(
            f"[{USER_INPUT}] | Task=语音播报开关 | session={session_id[:8]}, "
            f"enabled={enabled}, has_voice={session.has_voice_runtime}"
        )

    async def close_session(self, session_id: str) -> None:
        await self.interrupt_session_response(session_id, reason="session_close")
        session = self._sessions.pop(session_id, None)
        if session is not None:
            await session.session_ctx.on_session_end()
        logger.info(
            f"[{SESSION_END}] | Task=Soul会话清理 | session={session_id[:8]}, "
            f"active_sessions={len(self._sessions)}"
        )

    async def interrupt_session_response(
        self,
        session_id: str,
        *,
        reason: str = "user_stop_button",
    ) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False

        interrupted = False
        current_task = asyncio.current_task()
        active_task = session.active_response_task
        if active_task is not None and active_task is not current_task and not active_task.done():
            active_task.cancel()
            interrupted = True

        for future in list(session.pending_http_replies):
            if not future.done():
                future.cancel()
                interrupted = True
            try:
                session.pending_http_replies.remove(future)
            except ValueError:
                pass

        await self._interrupt_voice_runtime(session, reason=reason)
        await self._publish_response_interrupted(session, reason=reason)
        logger.info(
            f"[{AI_REPLY}] | Task=回复中断 | session={session.session_id[:8]}, "
            f"interrupted={interrupted}, reason={reason}"
        )
        return interrupted

    async def handle_user_text(
        self,
        session: ConversationSession,
        text: str,
        *,
        timeout_seconds: float,
        source: str,
    ) -> Tuple[str, str, Optional[Dict[str, Any]], Optional[str], str]:
        del timeout_seconds
        user_text = text.strip()
        if not user_text:
            raise HTTPException(status_code=400, detail="Text is required")

        current_task = asyncio.current_task()
        if current_task is not None:
            session.active_response_task = current_task

        trace_recorder = get_trace_recorder()
        trace_context = trace_recorder.start_trace(
            source=f"conversation.{source}",
            session_id=session.session_id,
            audience=session.audience,
            attributes={
                "conversation_id": session.conversation_id,
                "has_voice_runtime": session.has_voice_runtime,
                "voice_reply_enabled": session.voice_reply_enabled,
            },
        )
        trace_id = str(trace_context.get("trace_id") or "")

        try:
            async with session._lock:
                logger.info(
                    f"[{USER_INPUT}] | Task=Soul文本输入 | session={session.session_id[:8]}, "
                    f"source={source}, audience={session.audience}, has_voice={session.has_voice_runtime}, "
                    f"voice_reply={session.voice_reply_enabled}, text='{flatten_content(user_text, max_len=80)}'"
                )
                previous_messages = list(session.recent_messages[-12:])
                await session.session_ctx.add_message("user", user_text)
                session.record_message("user", user_text)
                response_message_id = str(uuid4())
                response_block_id = "main"

                async def publish_progress(payload: Dict[str, Any]) -> None:
                    if payload.get("type") == "assistant_sources":
                        payload = dict(payload)
                        payload.setdefault("message_id", response_message_id)
                        payload.setdefault("source", "soul_companion:agent")
                    await session.publish_text_event(payload)
                    if session.voice_connection is not None:
                        try:
                            session.voice_connection.send_app_message(payload)
                        except Exception as exc:
                            logger.warning(f"[{AI_REPLY}] | Task=Soul过程分发 | 前端过程发送失败: {exc}")

                streamed_reply = False
                stream_block_started = False
                stream_delta_buffer = ""
                stream_delta_last_flush_at = time.monotonic()
                assistant_first_token_at: Optional[str] = None

                def mark_assistant_first_token() -> str:
                    nonlocal assistant_first_token_at
                    if assistant_first_token_at is None:
                        assistant_first_token_at = _utc_iso_now()
                    return assistant_first_token_at

                async def publish_stream_payload(payload: Dict[str, Any]) -> None:
                    await session.publish_text_event(payload)
                    if session.voice_connection is not None:
                        try:
                            session.voice_connection.send_app_message(payload)
                        except Exception as exc:
                            logger.warning(f"[{AI_REPLY}] | Task=Soul流式文本分发 | 前端文字发送失败: {exc}")

                async def ensure_stream_block_started() -> None:
                    nonlocal stream_block_started
                    if stream_block_started:
                        return
                    stream_block_started = True
                    await publish_stream_payload({
                        "type": "assistant_message_start",
                        "message_id": response_message_id,
                        "source": "soul_companion:agent",
                    })
                    await publish_stream_payload({
                        "type": "content_block_start",
                        "message_id": response_message_id,
                        "block_id": response_block_id,
                        "block_type": "markdown",
                        "source": "soul_companion:agent",
                    })

                def should_flush_stream_delta(buffer: str, chunk: str) -> bool:
                    if len(buffer) >= STREAM_DELTA_MAX_CHARS:
                        return True
                    if len(buffer) >= STREAM_DELTA_MIN_CHARS and chunk[-1:] in STREAM_DELTA_BREAK_CHARS:
                        return True
                    return (
                        len(buffer) >= STREAM_DELTA_MIN_CHARS
                        and time.monotonic() - stream_delta_last_flush_at >= STREAM_DELTA_MAX_DELAY_SECONDS
                    )

                async def flush_stream_delta() -> None:
                    nonlocal streamed_reply, stream_delta_buffer, stream_delta_last_flush_at
                    if not stream_delta_buffer:
                        return
                    await ensure_stream_block_started()
                    streamed_reply = True
                    payload: Dict[str, Any] = {
                        "type": "content_block_delta",
                        "message_id": response_message_id,
                        "block_id": response_block_id,
                        "delta": stream_delta_buffer,
                    }
                    if assistant_first_token_at:
                        payload["first_token_at"] = assistant_first_token_at
                    await publish_stream_payload(payload)
                    stream_delta_buffer = ""
                    stream_delta_last_flush_at = time.monotonic()

                async def publish_stream_token(chunk: str) -> None:
                    nonlocal stream_delta_buffer
                    if not chunk:
                        return
                    mark_assistant_first_token()
                    stream_delta_buffer += chunk
                    if should_flush_stream_delta(stream_delta_buffer, chunk):
                        await flush_stream_delta()

                default_location = await default_location_service.resolve(
                    session_id=session.session_id,
                    user_id=session.user_id,
                    client_ip=session.client_ip,
                )
                default_location_context = {
                    **default_location.to_prompt_context(),
                    "session_id": session.session_id,
                    "user_id": session.user_id,
                    "client_ip": session.client_ip,
                }

                result = await answer_user_text(
                    user_text,
                    recent_messages=previous_messages,
                    allow_agent=(source == "text"),
                    progress_callback=publish_progress,
                    stream_callback=publish_stream_token,
                    reminder_context={
                        "session_id": session.session_id,
                        "conversation_id": session.conversation_id,
                        "audience": session.audience,
                        "user_id": session.user_id,
                        "client_ip": session.client_ip,
                        "source_text": user_text,
                    },
                    default_location_context=default_location_context,
                )
                await flush_stream_delta()
                reply = _normalize_assistant_reply_text(result.text, artifact=result.artifact)
                if not streamed_reply:
                    assistant_first_token_at = (
                        await self.stream_assistant_text(
                            session,
                            reply,
                            source=result.source,
                            message_id=response_message_id,
                        )
                    ) or assistant_first_token_at
                else:
                    finish_payload: Dict[str, Any] = {
                        "type": "assistant_message_finish",
                        "message_id": response_message_id,
                        "text": reply,
                        "source": result.source,
                    }
                    if assistant_first_token_at:
                        finish_payload["first_token_at"] = assistant_first_token_at
                    frontend_artifact = public_artifact(result.artifact)
                    await publish_stream_payload({
                        "type": "content_block_finish",
                        "message_id": response_message_id,
                        "block_id": response_block_id,
                    })
                    if frontend_artifact:
                        finish_payload["artifact"] = frontend_artifact
                    await publish_stream_payload(finish_payload)
                await self.dispatch_assistant_text(
                    session,
                    reply,
                    source=result.source,
                    artifact=result.artifact,
                    first_token_at=assistant_first_token_at or mark_assistant_first_token(),
                    message_id=response_message_id,
                )
                await self.dispatch_voice_speech(session, reply)
                logger.info(
                    f"[{AI_REPLY}] | Task=Soul文本回复 | session={session.session_id[:8]}, "
                    f"message_id={response_message_id}, source={result.source}, "
                    f"voice_reply={session.voice_reply_enabled}, "
                    f"content='{flatten_content(reply, max_len=80)}'"
                )
                trace_recorder.finish_trace(trace_id, status="success")
                return reply, result.source, result.artifact, assistant_first_token_at, response_message_id
        except asyncio.CancelledError:
            trace_recorder.finish_trace(trace_id, status="failed", error="cancelled")
            await self._publish_response_interrupted(session, reason="cancelled")
            raise
        except Exception as exc:
            trace_recorder.finish_trace(trace_id, status="failed", error=exc)
            raise
        finally:
            if session.active_response_task is current_task:
                session.active_response_task = None

    async def retry_task(
        self,
        session: ConversationSession,
        retry_token: str,
        *,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        del session, retry_token, timeout_seconds
        raise HTTPException(status_code=410, detail="旧任务重试接口已移除")

    async def _publish_response_interrupted(
        self,
        session: ConversationSession,
        *,
        reason: str,
    ) -> None:
        payload = {
            "type": "assistant_text_interrupted",
            "reason": reason,
        }
        await session.publish_text_event(payload)
        if session.voice_connection is not None:
            try:
                session.voice_connection.send_app_message(payload)
            except Exception as exc:
                logger.warning(f"[{AI_REPLY}] | Task=回复中断 | 前端通知失败: {exc}")

    async def _interrupt_voice_runtime(
        self,
        session: ConversationSession,
        *,
        reason: str,
    ) -> None:
        components = session.voice_components
        if components is not None:
            tts_processor = getattr(components, "tts_processor", None)
            if tts_processor is not None:
                try:
                    tts_processor.cancel_synthesis()
                except Exception as exc:
                    logger.warning(f"[{TTS}] | Task=语音中断 | TTS取消失败: {exc}")
        voice_runtime = session.voice_task or session.voice_connection
        interrupt = getattr(voice_runtime, "interrupt", None)
        if interrupt is None:
            return
        try:
            result = interrupt()
            if asyncio.iscoroutine(result):
                await result
            logger.debug(
                f"[{AI_REPLY}] | Task=语音中断 | session={session.session_id[:8]}, reason={reason}"
            )
        except Exception as exc:
            logger.warning(f"[{AI_REPLY}] | Task=语音中断 | runtime interrupt 失败: {exc}")

    async def dispatch_assistant_text(
        self,
        session: ConversationSession,
        text: str,
        *,
        source: str,
        artifact: Optional[Dict[str, Any]] = None,
        first_token_at: Optional[str] = None,
        message_id: Optional[str] = None,
        resolve_http_reply: bool = True,
    ) -> bool:
        if artifact:
            session.remember_task_artifact(artifact)
        frontend_artifact = public_artifact(artifact)
        handled_by_http = False
        if resolve_http_reply:
            handled_by_http = self._resolve_pending_http_reply(
                session,
                text,
                source=source,
                artifact=frontend_artifact,
                first_token_at=first_token_at,
                message_id=message_id,
            )
        if not handled_by_http:
            payload: Dict[str, Any] = {
                "type": "assistant_text",
                "text": text,
                "source": source,
            }
            if message_id:
                payload["message_id"] = message_id
            if first_token_at:
                payload["first_token_at"] = first_token_at
            if frontend_artifact:
                payload["artifact"] = frontend_artifact
            await session.publish_text_event(payload)
            if session.voice_connection is not None:
                try:
                    session.voice_connection.send_app_message(payload)
                except Exception as exc:
                    logger.warning(f"[{AI_REPLY}] | Task=Soul文本分发 | 前端文字发送失败: {exc}")

        await session.session_ctx.add_message(
            "assistant",
            text,
            source=source,
            artifact=frontend_artifact,
        )
        session.record_message("assistant", text)
        return handled_by_http

    async def _deliver_reminder_job(self, job: ReminderJob) -> None:
        session = self._sessions.get(job.session_id)
        if session is None:
            session = await self.get_or_create(
                audience=job.audience or "Aini",
                session_id=job.session_id,
                conversation_id=job.conversation_id,
                user_id=job.user_id,
                client_ip=job.client_ip,
            )
        delivered_job = job.with_updates(
            status="delivered",
            delivered_at=datetime.now().replace(microsecond=0).isoformat(),
            error="",
        )
        text = _normalize_assistant_reply_text(reminder_due_text(delivered_job))
        artifact = {
            "tool": "reminder",
            "status": "delivered",
            "reminder": delivered_job.to_dict(),
        }
        message_id = str(uuid4())
        async with session._lock:
            first_token_at = await self.stream_assistant_text(
                session,
                text,
                source="soul_companion:reminder",
                message_id=message_id,
            )
            await self.dispatch_assistant_text(
                session,
                text,
                source="soul_companion:reminder",
                artifact=artifact,
                first_token_at=first_token_at,
                message_id=message_id,
                resolve_http_reply=False,
            )
            await self.dispatch_voice_speech(session, text)
        logger.info(
            f"[{AI_REPLY}] | Task=提醒到期投递 | session={session.session_id[:8]}, "
            f"job={delivered_job.id}, message='{flatten_content(delivered_job.message, max_len=80)}'"
        )

    async def stream_assistant_text(
        self,
        session: ConversationSession,
        text: str,
        *,
        source: str,
        message_id: Optional[str] = None,
    ) -> Optional[str]:
        if not text or not session.text_progress_subscribers:
            return None
        chunks = _iter_text_stream_chunks(text)
        if not chunks:
            return None
        response_message_id = message_id or str(uuid4())
        block_id = "main"
        first_token_at: Optional[str] = None
        logger.debug(
            f"[{AI_REPLY}] | Task=Soul文本流式输出 | session={session.session_id[:8]}, "
            f"source={source}, chunks={len(chunks)}"
        )
        await session.publish_text_event({
            "type": "assistant_message_start",
            "message_id": response_message_id,
            "source": source,
        })
        await session.publish_text_event({
            "type": "content_block_start",
            "message_id": response_message_id,
            "block_id": block_id,
            "block_type": "markdown",
            "source": source,
        })
        for chunk in chunks:
            if first_token_at is None:
                first_token_at = _utc_iso_now()
            await session.publish_text_event({
                "type": "content_block_delta",
                "message_id": response_message_id,
                "block_id": block_id,
                "delta": chunk,
                "first_token_at": first_token_at,
            })
            await asyncio.sleep(TEXT_STREAM_CHUNK_DELAY_SECONDS)
        await session.publish_text_event({
            "type": "content_block_finish",
            "message_id": response_message_id,
            "block_id": block_id,
        })
        await session.publish_text_event({
            "type": "assistant_message_finish",
            "message_id": response_message_id,
            "text": text,
            "source": source,
            "first_token_at": first_token_at,
        })
        return first_token_at

    async def dispatch_voice_speech(
        self,
        session: ConversationSession,
        text: str,
        *,
        metadata: Optional[dict] = None,
    ) -> None:
        del metadata
        if not session.voice_reply_enabled:
            return
        if session.voice_task is None:
            logger.warning(f"[{TTS}] | Task=语音播报跳过 | session={session.session_id[:8]}, reason=voice_runtime_missing")
            return
        components = session.voice_components
        speak_text = getattr(session.voice_connection, "speak_text", None)
        if speak_text is not None:
            try:
                result = speak_text(text)
                if asyncio.iscoroutine(result):
                    await result
                return
            except Exception as exc:
                logger.warning(
                    f"[{AI_REPLY}] | Task=语音播报 | runtime speak_text 失败，文本回复不受影响: "
                    f"session={session.session_id[:8]}, error={exc}"
                )
                return
        if components is None or getattr(components, "tts_processor", None) is None:
            logger.warning(f"[{TTS}] | Task=语音播报跳过 | session={session.session_id[:8]}, reason=tts_processor_missing")
            return
        try:
            components.tts_processor.cancel_synthesis()
            logger.info(
                f"[{TTS}] | Task=语音播报跳过 | session={session.session_id[:8]}, reason=legacy_runtime_removed, "
                f"text='{flatten_content(text, max_len=80)}'"
            )
        except Exception as exc:
            logger.warning(
                f"[{AI_REPLY}] | Task=语音播报 | TTS入队失败，文本回复不受影响: "
                f"session={session.session_id[:8]}, error={exc}"
            )

    def _resolve_pending_http_reply(
        self,
        session: ConversationSession,
        text: str,
        *,
        source: str,
        artifact: Optional[Dict[str, Any]] = None,
        first_token_at: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> bool:
        while session.pending_http_replies:
            future = session.pending_http_replies.pop(0)
            if future.cancelled() or future.done():
                continue
            future.set_result((text, source, artifact, first_token_at, message_id))
            return True
        return False


conversation_session_manager = ConversationSessionManager()
