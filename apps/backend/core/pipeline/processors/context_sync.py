"""
ContextSyncProcessor — Pipeline 内 LLM 上下文同步处理器

位于 user_aggregator → llm 之间。
拦截 LLMContextFrame，在 LLM 读取 context.get_messages() 之前：
1. 清理过期的 emotion hint（动态注入的 system 消息）
2. 从 SQL 注入历史摘要 + 事件记忆
3. 截断过长的对话历史
4. 重组 messages 列表

这是整个 Pipeline 中唯一能同时做到"清理 + 注入 + 截断"的位置。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from loguru import logger
from core.logging_utils import STARTUP, CONTEXT_SYNC, truncate_content, flatten_content
from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

if TYPE_CHECKING:
    from core.conversation.context_manager import AsyncContextManager
    from core.conversation.sql_store import SQLStore
    from core.conversation.file_store import MemoryFileStore


class ContextSyncProcessor(FrameProcessor):
    """
    在 LLMContextFrame 到达 LLM 之前，同步上下文：
    - 清除过期 emotion hint
    - 注入 SQL 长期记忆
    - 截断历史保持 token 可控（截断的消息送入 AsyncContextManager 分析队列）
    """

    # emotion hint 的识别标记（EmotionProcessor 注入的 system 消息都包含这些关键词之一）
    _HINT_MARKERS = frozenset([
        "用户语气", "用户情绪", "情绪提示", "emotion_hint",
        "用户当前情绪", "回复风格建议",
    ])

    def __init__(
        self,
        *,
        sql_store: Optional["SQLStore"] = None,
        session_id: str = "",
        speaker_id: str = "",
        max_context_messages: int = 30,
        summary_limit: int = 5,
        events_limit: int = 20,
    ):
        super().__init__()
        self._sql = sql_store
        self._session_id = session_id
        self._speaker_id = speaker_id
        self._user_id: str = ""
        self._max_context_messages = max_context_messages
        self._summary_limit = summary_limit
        self._events_limit = events_limit
        # 记录 system_prompt 的内容 hash，用于识别人设 prompt
        self._system_prompt_content: Optional[str] = None
        # AsyncContextManager 引用（可选，用于截断时送入分析队列）
        self._context_manager: Optional["AsyncContextManager"] = None
        self._audience: str = ""
        # MemoryFileStore 引用（可选，用于从文件加载持久化记忆）
        self._file_store: Optional["MemoryFileStore"] = None
        # ── 记忆缓存（原始数据，在 _fetch_memory_messages 中统一格式化）──
        # 持久化记忆：用户建立连接时按配置从文件或 DB 串行加载（历史摘要 + 事实）
        self._persistent_summaries: List[Dict] = []
        self._persistent_events: List[Dict] = []
        self._persistent_memory_ids: Set[int] = set()
        self._persistent_loaded: bool = False
        # 实时重要记忆：会话中对话轮数溢出后 LLM 异步提取，完成后更新此缓存
        self._realtime_summaries: List[Dict] = []
        self._realtime_events: List[Dict] = []
        self._realtime_memory_ids: Set[int] = set()
        # 过往记忆：首次连接从 DB 加载，只读，不参与截断/双缓冲
        self._past_summaries: List[Dict] = []
        self._past_events: List[Dict] = []
        self._past_loaded: bool = False
        self._memory_lock: asyncio.Lock = asyncio.Lock()
        # ── 双缓冲：暂存被截断但尚未被 LLM 总结的旧对话 ──
        # 截断时将旧消息存入此列表，待 push_new_memories() 确认总结完成后清空
        self._pending_context: List[Dict[str, str]] = []
        self._pending_summarized: bool = False  # LLM 总结完成的标志

        logger.info(
            f"[{STARTUP}] ContextSync 初始化: session={session_id}, "
            f"max_context={max_context_messages}, "
            f"summary_limit={summary_limit}, events_limit={events_limit}, "
            f"sql={'有' if sql_store else '无'}"
        )

    def set_sql_store(self, sql_store: "SQLStore") -> None:
        """延迟注入 SQL store（Pipeline 创建时可能还没有）"""
        self._sql = sql_store

    def set_file_store(self, file_store: "MemoryFileStore") -> None:
        """延迟注入 MemoryFileStore（用于从文件加载持久化记忆）"""
        self._file_store = file_store

    def set_session_info(self, session_id: str, speaker_id: str) -> None:
        """延迟注入 session 信息"""
        self._session_id = session_id
        self._speaker_id = speaker_id

    def set_context_manager(
        self,
        context_manager: "AsyncContextManager",
        audience: str,
    ) -> None:
        """注入 AsyncContextManager，截断时将丢弃的消息送入分析队列"""
        self._context_manager = context_manager
        self._audience = audience

    def set_user_id(self, user_id: str) -> None:
        """设置鉴权后的用户唯一标识（供 get_events 多级身份查询使用）"""
        self._user_id = user_id

    def invalidate_memory_cache(self) -> None:
        """会话结束时调用，清除所有记忆缓存（下次连接时重新加载）"""
        self._persistent_summaries = []
        self._persistent_events = []
        self._persistent_memory_ids = set()
        self._persistent_loaded = False
        self._realtime_summaries = []
        self._realtime_events = []
        self._realtime_memory_ids = set()
        self._past_summaries = []
        self._past_events = []
        self._past_loaded = False
        # 双缓冲状态也一并清理
        self._pending_context = []
        self._pending_summarized = False

    async def preload_persistent_memory(self) -> None:
        """
        在用户建立连接时串行加载持久化记忆（历史摘要 + 事实）以及过往记忆（DB 最近 5 天）。

        由 webrtc.py 在注入所有 session 信息（set_user_id 等）后同步调用，
        确保第一次 LLM 调用前持久化记忆已就绪。

        file_store 存在时只从文件加载；否则从 DB 查询。
        过往记忆（_past_*）始终从 DB 查询（跨会话数据，仅加载最近 5 天）。

        支持 3 级身份查询：
        1. 未登录：session_id + audiences
        2. 已登录 + 无 speaker_id：user_id + audiences
        3. 已登录 + speaker_id：仅 speaker_id + audiences
        """
        async with self._memory_lock:
            if not self._persistent_loaded:
                if self._file_store is not None and self._audience:
                    try:
                        loaded = await self._file_store.load_from_file(
                            user_id=self._user_id,
                            speaker_id=self._speaker_id,
                            session_id=self._session_id,
                            audiences=self._audience,
                        )
                        if loaded:
                            summaries = self._file_store.get_summaries(
                                audiences=self._audience,
                                user_id=self._user_id,
                                speaker_id=self._speaker_id,
                                session_id=self._session_id,
                                limit=self._summary_limit,
                            )
                            events = self._file_store.get_events(
                                audiences=self._audience,
                                user_id=self._user_id,
                                speaker_id=self._speaker_id,
                                session_id=self._session_id,
                                limit=self._events_limit,
                            )
                            self._persistent_summaries = summaries
                            self._persistent_events = events
                            self._persistent_memory_ids = {
                                r["id"] for r in summaries + events if r.get("id")
                            }
                            logger.info(
                                f"[{CONTEXT_SYNC}] | Task=加载持久化记忆 | 从文件预加载完成: "
                                f"session={self._session_id}, "
                                f"summaries={len(summaries)}条, events={len(events)}条"
                            )
                        else:
                            self._persistent_summaries = []
                            self._persistent_events = []
                            self._persistent_memory_ids = set()
                            logger.info(
                                f"[{CONTEXT_SYNC}] | Task=加载持久化记忆 | 文件中无持久化记忆: "
                                f"session={self._session_id}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"[{CONTEXT_SYNC}] | Task=加载持久化记忆 | 文件加载失败: "
                            f"session={self._session_id}, error={e}"
                        )
                    self._persistent_loaded = True
                elif self._sql is not None:
                    try:
                        summaries, events = await self._query_memory_from_db_raw()
                        self._persistent_summaries = summaries
                        self._persistent_events = events
                        self._persistent_memory_ids = {
                            r["id"] for r in summaries + events if r.get("id")
                        }
                        logger.info(
                            f"[{CONTEXT_SYNC}] | Task=加载持久化记忆 | 串行预加载完成: "
                            f"session={self._session_id}, "
                            f"summaries={len(summaries)}条, events={len(events)}条"
                        )
                    except Exception as e:
                        logger.error(
                            f"[{CONTEXT_SYNC}] | Task=加载持久化记忆 | 预加载失败: "
                            f"session={self._session_id}, error={e}"
                        )
                    self._persistent_loaded = True
                else:
                    self._persistent_loaded = True

            # ── 从 DB 加载过往记忆（最近 5 天，只读）──
            if not self._past_loaded and self._sql is not None and self._audience:
                try:
                    past_summaries, past_events = await self._query_past_memory_from_db()
                    self._past_summaries = past_summaries
                    self._past_events = past_events
                    self._past_loaded = True
                    logger.info(
                        f"[{CONTEXT_SYNC}] | Task=加载过往记忆 | DB查询完成: "
                        f"session={self._session_id}, "
                        f"past_summaries={len(past_summaries)}条, "
                        f"past_events={len(past_events)}条"
                    )
                except Exception as e:
                    logger.error(
                        f"[{CONTEXT_SYNC}] | Task=加载过往记忆 | DB查询失败: "
                        f"session={self._session_id}, error={e}"
                    )

    def push_new_memories(self, memories: List[Dict[str, Any]]) -> None:
        """
        将 LLM 新提取的记忆推入实时记忆缓存（不查询 DB）。

        LLM 作为 Memory Integrator，输出的摘要和事实会替换实时缓存。

        Args:
            memories: LLM 分析输出的记忆列表，每条包含
                      msg_type / content_type / contents / importance 等字段
        """
        if not memories:
            return

        rules = None
        if self._sql is not None:
            rules = self._sql._rules

        summary_msg_type = rules.summary_msg_type if rules else "对话摘要"

        new_summaries: List[Dict[str, Any]] = []
        new_events: List[Dict[str, Any]] = []

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for m in memories:
            msg_type = m.get("msg_type", "")
            contents = m.get("contents", "")
            if not contents:
                continue
            if msg_type == summary_msg_type:
                new_summaries.append({
                    "create_time": now_str,
                    "contents": contents,
                })
            else:
                new_events.append({
                    "content_type": m.get("content_type", ""),
                    "contents": contents,
                    "importance": m.get("importance", 5),
                })

        total_new = len(new_summaries) + len(new_events)
        if total_new:
            if new_summaries:
                self._realtime_summaries = new_summaries
            if new_events:
                self._realtime_events = new_events
            # 双缓冲：标记 pending 已被总结，下次 _sync_context 时清空 _pending_context
            if self._pending_context and not self._pending_summarized:
                self._pending_summarized = True
                logger.info(
                    f"[{CONTEXT_SYNC}] | Task=双缓冲-总结完成 | session={self._session_id}, "
                    f"LLM总结完成，pending_size={len(self._pending_context)}条，"
                    f"下次_sync_context时将清空pending_context"
                )
            logger.debug(
                f"[{CONTEXT_SYNC}] | Task=推送实时记忆 | session={self._session_id}, "
                f"更新实时记忆={total_new}条 "
                f"(summaries={len(new_summaries)}, events={len(new_events)})"
            )
        else:
            logger.debug(
                f"[{CONTEXT_SYNC}] | Task=推送实时记忆 | session={self._session_id}, 无新增实时记忆"
            )

    @property
    def max_context_messages(self) -> int:
        """返回当前生效的最大上下文消息数。"""
        return self._max_context_messages

    def set_max_context_messages(self, max_context_messages: int) -> None:
        """更新最大上下文消息数（供 persona 覆盖全局默认值）"""
        self._max_context_messages = max_context_messages

    def set_summary_limit(self, summary_limit: int) -> None:
        """更新摘要条数限制（供 persona 覆盖全局默认值）"""
        self._summary_limit = summary_limit

    def set_events_limit(self, events_limit: int) -> None:
        """更新事件条数限制（供 persona 覆盖全局默认值）"""
        self._events_limit = events_limit

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMContextFrame):
            await self._sync_context(frame.context)
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _sync_context(self, context: Any) -> None:
        """核心同步逻辑：清理 → 注入 → 截断 → 重组"""
        messages = context.get_messages()
        original_count = len(messages)

        # ── 双缓冲状态日志 ──
        logger.debug(
            f"[{CONTEXT_SYNC}] | Task=双缓冲-状态 | session={self._session_id}, "
            f"pending_size={len(self._pending_context)}, "
            f"pending_summarized={self._pending_summarized}"
        )

        # ── Step 1: 分离消息类型 ──
        static_system: List[Dict[str, str]] = []     # 人设 prompt
        injected_system: List[Dict[str, str]] = []    # 之前注入的 SQL 摘要/事件（清除）
        emotion_hints: List[Dict[str, str]] = []      # emotion hint（清除）
        conversation: List[Dict[str, str]] = []       # user/assistant 对话

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                if self._is_emotion_hint(content):
                    emotion_hints.append(msg)
                elif self._is_injected_memory(content):
                    injected_system.append(msg)
                elif not static_system:
                    # 第一个 system 消息视为人设 prompt
                    static_system.append(msg)
                    self._system_prompt_content = content
                elif content == self._system_prompt_content:
                    # 重复的人设 prompt，跳过
                    pass
                else:
                    # 其他 system 消息（可能是 FlowManager 注入的节点 role_messages）
                    static_system.append(msg)
            else:
                conversation.append(msg)

        # ── Step 1.5: 去除连续重复的对话消息 ──
        if conversation:
            deduped: List[Dict[str, str]] = [conversation[0]]
            for msg in conversation[1:]:
                prev = deduped[-1]
                if msg.get("role") == prev.get("role") and msg.get("content") == prev.get("content"):
                    continue
                deduped.append(msg)
            if len(deduped) < len(conversation):
                logger.debug(
                    f"[{CONTEXT_SYNC}] | Task=去重 | session={self._session_id}, "
                    f"原始={len(conversation)} → 去重后={len(deduped)}"
                )
                conversation = deduped

        # ── Step 1.6: 过滤 function call 中间消息 ──
        # 工具调用消息（role=assistant, content 为空, 含 tool_calls）和工具结果消息
        # （role=tool/function）是 Pipecat 在当轮函数调用内部使用的中间帧，
        # 不应保留在跨轮 LLM 上下文或记忆分析队列中。
        if conversation:
            filtered: List[Dict[str, str]] = []
            for msg in conversation:
                role = msg.get("role", "")
                if role in ("tool", "function"):
                    continue
                has_empty_content = not (msg.get("content") or "").strip()
                has_tool_calls = bool(msg.get("tool_calls"))
                if role == "assistant" and has_empty_content and has_tool_calls:
                    continue
                filtered.append(msg)
            if len(filtered) < len(conversation):
                logger.debug(
                    f"[{CONTEXT_SYNC}] | Task=过滤工具消息 | session={self._session_id}, "
                    f"原始={len(conversation)} → 过滤后={len(filtered)}"
                )
                conversation = filtered

        # ── Step 1.7: 过滤 wait_hint 等标记了 exclude_from_llm_history 的 assistant 消息 ──
        if conversation:
            before = len(conversation)
            conversation = [
                m for m in conversation
                if not (m.get("metadata") or {}).get("exclude_from_llm_history")
            ]
            if len(conversation) != before:
                logger.debug(
                    f"[{CONTEXT_SYNC}] | Task=过滤wait_hint | session={self._session_id}, "
                    f"原始={before} → 过滤后={len(conversation)}"
                )

        # ── 双缓冲：若 LLM 已完成总结，优先清空 _pending_context ──
        # 在截断判断之前清理，确保新的截断可以立即使用新的 pending 字段
        just_cleared_pending = False
        if self._pending_summarized:
            cleared_count = len(self._pending_context)
            self._pending_context = []
            self._pending_summarized = False
            just_cleared_pending = True
            logger.info(
                f"[{CONTEXT_SYNC}] | Task=双缓冲-清除pending | session={self._session_id}, "
                f"总结已完成，清空pending_context={cleared_count}条，summary已通过memory注入"
            )

        # ── Step 2: 截断对话历史（双缓冲）──
        if len(conversation) > self._max_context_messages:
            cut = self._max_context_messages - len(conversation)
            truncated_messages = conversation[:cut]
            conversation = conversation[cut:]
            # 双缓冲：将截断消息暂存到 _pending_context（而非立即丢弃）
            # 只在 pending 为空且本轮未刚清空总结的 pending 时设置，
            # 避免覆盖尚未被总结的旧 pending，也避免把刚总结完的旧消息再放回来
            if not self._pending_context and not just_cleared_pending:
                self._pending_context = truncated_messages
                self._pending_summarized = False
                logger.info(
                    f"[{CONTEXT_SYNC}] | Task=双缓冲-截断暂存 | session={self._session_id}, "
                    f"截断={len(truncated_messages)}条, "
                    f"pending_size={len(self._pending_context)}"
                )
            if just_cleared_pending:
                logger.info(
                    f"[{CONTEXT_SYNC}] | Task=双缓冲-截断跳过 | session={self._session_id}, "
                    f"截断={len(truncated_messages)}条已被总结，跳过暂存和重复分析"
                )
            # 将截断的消息异步送入记忆分析队列，不白扔
            # 若本轮刚清空已总结的 pending，则这批截断消息已被分析过，跳过重复入队
            if (
                not just_cleared_pending
                and self._context_manager is not None
                and self._session_id
                and self._audience
            ):
                task = asyncio.create_task(
                    self._context_manager.queue_truncated_messages(
                        namespace=f"{self._audience}:{self._session_id}",
                        session_id=self._session_id,
                        speaker_id=self._speaker_id,
                        audience=self._audience,
                        messages=truncated_messages,
                        user_id=self._user_id,
                    )
                )
                task.add_done_callback(
                    lambda t: logger.error(
                        f"[{CONTEXT_SYNC}] | Task=对话截断 | 异步, 截断消息送入分析队列异常: {t.exception()}"
                    ) if not t.cancelled() and t.exception() else None
                )

        # ── 双缓冲：将 _pending_context 合并到 conversation 前（保持上下文连续性）──
        if self._pending_context:
            conversation = self._pending_context + conversation
            logger.debug(
                f"[{CONTEXT_SYNC}] | Task=双缓冲-保留合并 | session={self._session_id}, "
                f"合并pending={len(self._pending_context)}条到conversation前, "
                f"合并后conversation={len(conversation)}条"
            )

        # ── Step 3: 从 SQL 注入长期记忆 ──
        memory_messages: List[Dict[str, str]] = []
        if self._sql is not None and self._session_id:
            memory_messages = await self._fetch_memory_messages()

        # ── Step 4: 重组 messages ──
        new_messages = static_system + memory_messages + conversation
        context.set_messages(new_messages)

        # 构建 conv_list 预览（每条消息截断展示）
        conv_list_preview = [truncate_content(m.get('content', ''), 30) for m in conversation]

        # 构建 memory_preview：section header 在前，memory[i]: [label] 在后
        if memory_messages:
            preview_parts = []
            for i, mm in enumerate(memory_messages):
                content = mm.get("content", "")
                # content 格式: "[label]\n【section】\n...data..."
                lines = content.split("\n", 2)
                if len(lines) >= 2:
                    label_line = lines[0]       # e.g. "[实时重要记忆]"
                    section_header = lines[1]   # e.g. "【对话摘要】"
                    data = lines[2] if len(lines) > 2 else ""
                    preview_parts.append(f"{section_header}\nmemory[{i}]: {label_line}\n{data}")
                else:
                    preview_parts.append(f"memory[{i}]: {content}")
            memory_preview = "\n\n".join(preview_parts)
        else:
            memory_preview = "memory: (无)"

        logger.debug(
            f"[{CONTEXT_SYNC}] | Task=上下文重组 | session={self._session_id}, "
            f"原始={original_count} → 最终={len(new_messages)} "
            f"(system={len(static_system)}, memory={len(memory_messages)}, "
            f"conv={len(conversation)})\n"
            f"system: {flatten_content(static_system[0].get('content', '') if static_system else '', 120)}\n"
            f"{memory_preview}\n"
            f"conv_last: {flatten_content(conversation[-1].get('content', '') if conversation else '', 120)}\n"
            f"conv_list: {conv_list_preview}"
        )

    async def _fetch_memory_messages(self) -> List[Dict[str, str]]:
        """
        返回过往记忆 + 实时重要记忆的分层列表，共最多 4 条 system 消息。

        注入顺序：[过往摘要] → [过往事实] → [实时摘要] → [实时事实]
        过往数据（_past_*）只读，不参与截断/双缓冲；
        实时数据（_realtime_*）在会话中动态更新。

        持久化记忆只使用连接时显式预加载的结果。
        """
        messages: List[Dict[str, str]] = []

        # ── 过往层：[过往摘要] + [过往事实]（只读，不随本次对话变化）──
        if self._past_loaded:
            past_summaries = self._past_summaries
            past_events = self._past_events
        else:
            past_summaries = []
            past_events = []

        if past_summaries:
            messages.extend(self._build_memory_messages(past_summaries, [], label="过往摘要"))
        if past_events:
            messages.extend(self._build_memory_messages([], past_events, label="过往事实"))

        # ── 实时层：[实时重要记忆]（本次会话动态更新）──
        if self._realtime_summaries or self._realtime_events:
            messages.extend(
                self._build_memory_messages(
                    self._realtime_summaries,
                    self._realtime_events,
                    label="实时重要记忆",
                )
            )

        return messages

    async def _query_past_memory_from_db(self) -> Tuple[List[Dict], List[Dict]]:
        """
        从 DB 并发查询过往摘要和事件（最近 5 天），返回原始行字典元组 (summaries, events)。

        3 级身份查询策略（同 _query_memory_from_db_raw）：
        1. 已登录 + speaker_id → 仅用 speaker_id
        2. 已登录 + 无 speaker_id → 仅用 user_id
        3. 未登录 → 仅用 session_id
        """
        # 根据 3 级身份确定查询参数
        if self._user_id and self._speaker_id:
            query_user_id = self._user_id
            query_speaker_id = self._speaker_id
            query_session_id = ""
            identity_desc = f"speaker_id={self._speaker_id}(仅speaker_id)"
        elif self._user_id:
            query_user_id = self._user_id
            query_speaker_id = ""
            query_session_id = ""
            identity_desc = f"user_id={self._user_id}"
        else:
            query_user_id = ""
            query_speaker_id = ""
            query_session_id = self._session_id
            identity_desc = f"session_id={self._session_id}"

        summaries_task = self._sql.get_past_summaries(
            self._audience,
            user_id=query_user_id,
            speaker_id=query_speaker_id,
            session_id=query_session_id,
            limit=self._summary_limit,
        )
        events_task = self._sql.get_past_events(
            self._audience,
            user_id=query_user_id,
            speaker_id=query_speaker_id,
            session_id=query_session_id,
            limit=self._events_limit,
        )

        summaries, events = await asyncio.gather(
            summaries_task, events_task,
            return_exceptions=True,
        )

        if isinstance(summaries, Exception):
            logger.error(
                f"[{CONTEXT_SYNC}] | Task=加载过往记忆-DB查询 | 查询过往摘要异常: {summaries}"
            )
            summaries = []
        if isinstance(events, Exception):
            logger.error(
                f"[{CONTEXT_SYNC}] | Task=加载过往记忆-DB查询 | 查询过往事件异常: {events}"
            )
            events = []

        logger.debug(
            f"[{CONTEXT_SYNC}] | Task=加载过往记忆-DB查询 | audiences={self._audience}, "
            f"identity=[{identity_desc}], "
            f"过往摘要={len(summaries)}条, 过往事件={len(events)}条"
        )

        return summaries, events

    async def _query_memory_from_db_raw(self) -> Tuple[List[Dict], List[Dict]]:
        """
        从 DB 并发查询摘要和事件，返回原始行字典元组 (summaries, events)。
        每行包含完整字段（含 id），供调用方按需格式化或对比 ID。

        3 级身份查询策略：
        1. 已登录 + speaker_id → 仅用 speaker_id
        2. 已登录 + 无 speaker_id → 仅用 user_id
        3. 未登录 → 仅用 session_id
        """
        summary_limit = self._summary_limit
        events_limit = self._events_limit

        # 根据 3 级身份确定查询参数
        if self._user_id and self._speaker_id:
            query_user_id = self._user_id
            query_speaker_id = self._speaker_id
            query_session_id = ""
            identity_desc = f"speaker_id={self._speaker_id}(仅speaker_id)"
        elif self._user_id:
            query_user_id = self._user_id
            query_speaker_id = ""
            query_session_id = ""
            identity_desc = f"user_id={self._user_id}"
        else:
            query_user_id = ""
            query_speaker_id = ""
            query_session_id = self._session_id
            identity_desc = f"session_id={self._session_id}"

        summaries_task = self._sql.get_summaries(
            self._audience,
            user_id=query_user_id,
            speaker_id=query_speaker_id,
            session_id=query_session_id,
            limit=summary_limit,
        )
        events_task = self._sql.get_events(
            self._audience,
            user_id=query_user_id,
            speaker_id=query_speaker_id,
            session_id=query_session_id,
            limit=events_limit,
        )

        summaries, events = await asyncio.gather(
            summaries_task, events_task,
            return_exceptions=True,
        )

        if isinstance(summaries, Exception):
            logger.error(
                f"[{CONTEXT_SYNC}] | Task=加载持久化记忆-DB查询 | 查询摘要异常: {summaries}"
            )
            summaries = []
        if isinstance(events, Exception):
            logger.error(
                f"[{CONTEXT_SYNC}] | Task=加载持久化记忆-DB查询 | 查询事件异常: {events}"
            )
            events = []

        # 查询结果日志
        summaries_preview = [
            truncate_content(s.get("contents", ""), 60) for s in summaries
        ] if summaries else []
        events_preview = [
            f"[{e.get('content_type', '')}] {e.get('contents', '')}" for e in events
        ] if events else []
        logger.debug(
            f"[{CONTEXT_SYNC}] | Task=加载持久化记忆-DB查询 | audiences={self._audience}, "
            f"identity=[{identity_desc}], "
            f"query=[get_summaries(limit={summary_limit}), "
            f"get_events(limit={events_limit})], "
            f"摘要={len(summaries)}条{summaries_preview}, "
            f"事件={len(events)}条{events_preview}"
        )

        return summaries, events

    @staticmethod
    def _build_memory_messages(
        summaries: List[Dict],
        events: List[Dict],
        label: str,
    ) -> List[Dict[str, str]]:
        """
        将摘要行和事件行分别格式化为带标签的 system 消息。

        Args:
            summaries: get_summaries() 返回的原始行字典列表
            events:    get_events() 返回的原始行字典列表
            label:     记忆区块标签，如 "持久化记忆"、"实时重要记忆" 或 "重要记忆"

        Returns:
            0 ~ 2 条 system 消息：摘要消息（memory[0]）+ 事实消息（memory[1]）；
            无内容时返回空列表。
        """
        messages: List[Dict[str, str]] = []

        if summaries:
            summary_text = "\n".join(
                f"[{s['create_time']}] {s['contents']}" for s in summaries
            )
            messages.append({
                "role": "system",
                "content": f"[{label}]\n【对话摘要】\n{summary_text}",
            })

        if events:
            event_text = "\n".join(
                f"- [{e['content_type']}] {e['contents']} "
                f"(重要度:{e['importance']})"
                for e in events
            )
            messages.append({
                "role": "system",
                "content": f"[{label}]\n【重要事实】\n{event_text}",
            })

        return messages

    async def _query_memory_from_db(self) -> List[Dict[str, str]]:
        """
        兼容旧调用路径：查询 DB 并返回格式化后的 system 消息列表。
        内部委托给 _query_memory_from_db_raw + _build_memory_messages。
        """
        summaries, events = await self._query_memory_from_db_raw()
        return self._build_memory_messages(summaries, events, label="持久化记忆")

    @classmethod
    def _is_emotion_hint(cls, content: str) -> bool:
        """判断是否为 emotion hint system 消息"""
        if not content:
            return False
        # 检查前 50 个字符是否包含 hint 标记
        prefix = content[:50]
        return any(marker in prefix for marker in cls._HINT_MARKERS)

    @staticmethod
    def _is_injected_memory(content: str) -> bool:
        """判断是否为之前注入的记忆消息（过往层 或 实时层）"""
        if not content:
            return False
        return (
            content.startswith("[过往摘要]")
            or content.startswith("[过往事实]")
            or content.startswith("[实时重要记忆]")
            or content.startswith("[持久化记忆]")
            or content.startswith("[重要记忆]")
        )
