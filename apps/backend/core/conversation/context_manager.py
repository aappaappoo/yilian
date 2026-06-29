"""
异步上下文管理器

职责：
1. 每轮对话消息缓存到内存
2. 异步调用 LLM 统一分析对话 → 生成摘要 + 提取事件（1次调用）
3. 将分析结果写入 PostgreSQL（msg_type / content_type / importance 全由 LLM 决定）
4. 构建给 LLM 的完整上下文

关键设计：
- 先 SQL 查询（已有分类 + 已有记忆），再 1 次 LLM 调用完成所有分析
- 支持 keep / new / expand / conflict 四种操作类型
- keep: LLM 判断已有记忆已充分覆盖，无需任何写操作
- 异步非阻塞，不影响对话流
- 每 N 条消息自动触发一次 LLM 分析存储
- 使用 asyncio.Lock 保证同一 session 的分析串行执行，杜绝并发重复写入
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from core.conversation.knowledge import KnowledgeRules, get_rules
from core.logging_utils import (
    STARTUP, MEM_SYS, CONTEXT_SYNC,
    truncate_content, flatten_content,
)
from core.conversation.sql_store import SQLStore
from core.conversation.file_store import MemoryFileStore
from core.conversation.models import MemoryWriteResult


class AsyncContextManager:
    """
    异步上下文管理器 — 核心类。
    每个 audience 共享一个实例，管理所有 session 的上下文生命周期。
    """

    def __init__(
            self,
            sql_store: SQLStore,
            llm_caller: Any,
            knowledge_rules: Optional[KnowledgeRules] = None,
            embedding_service: Optional[Any] = None,
            max_context_messages: int = 30,
            direct_write: bool = False,
            file_store: Optional[MemoryFileStore] = None,
    ) -> None:
        self._sql = sql_store
        self._llm_caller = llm_caller
        self._max_context_messages = max_context_messages
        self._direct_write = direct_write
        self._rules: KnowledgeRules = knowledge_rules if knowledge_rules is not None else get_rules()
        self._embedding_service = embedding_service
        self._context_sync_processor: Optional[Any] = None
        self._file_store: Optional[MemoryFileStore] = file_store

        self._message_buffer: Dict[str, List[Dict[str, str]]] = {}
        # 改为 per-session 的异步队列，保证分析严格串行
        self._analyze_queues: Dict[str, asyncio.Queue] = {}
        self._analyze_workers: Dict[str, asyncio.Task] = {}
        # 记录每个 session 上次成功分析时 buffer 的长度，用于避免重复分析
        self._last_analyzed_index: Dict[str, int] = {}
        self._embedding_tasks: set = set()
        # per-session buffer 锁，保护并发读写
        self._buffer_locks: Dict[str, asyncio.Lock] = {}
        # per-session 对话轮次计数器（user 消息每次到达时加 1）
        self._round_counters: Dict[str, int] = {}

        logger.info(
            f"[{STARTUP}] | Task=AsyncContextManager初始化 | 异步上下文管理器初始化: max_context_messages={max_context_messages}, "
            f"direct_write={direct_write}"
        )

    @staticmethod
    def _extract_json_from_text(text: str) -> Optional[str]:
        """
        从 LLM 返回的文本中尝试提取 JSON 数组。
        处理常见情况：
        1. 被 ```json ... ``` 包裹
        2. JSON 前后有多余文字
        3. 多段文本中混有 JSON
        """
        text = text.strip()

        # 情况 1：被 markdown 代码块包裹
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]).strip()

        # 情况 2：直接是合法 JSON
        if text.startswith("["):
            return text

        # 情况 3：从文本中提取最外层的 JSON 数组
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end >= start:
            return text[start : end + 1]

        return None

    def _get_analyze_queue(self, session_id: str) -> asyncio.Queue:
        """获取指定 session 的分析队列（惰性创建）"""
        if session_id not in self._analyze_queues:
            self._analyze_queues[session_id] = asyncio.Queue()
        return self._analyze_queues[session_id]

    def _get_buffer_lock(self, session_id: str) -> asyncio.Lock:
        """获取指定 session 的 buffer 锁（惰性创建）"""
        if session_id not in self._buffer_locks:
            self._buffer_locks[session_id] = asyncio.Lock()
        return self._buffer_locks[session_id]

    def _ensure_worker(self, session_id: str) -> None:
        """确保指定 session 有一个正在运行的 worker"""
        existing = self._analyze_workers.get(session_id)
        if existing and not existing.done():
            return
        task = asyncio.create_task(self._analyze_worker(session_id))
        self._analyze_workers[session_id] = task

    async def _analyze_worker(self, session_id: str) -> None:
        """
        Per-session 的分析 worker。
        从队列中逐个取出分析任务，严格串行执行。
        每次分析前都会从 SQL 读取最新的已有记忆，保证数据一致性。
        """
        queue = self._get_analyze_queue(session_id)
        while True:
            try:
                job = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                break

            try:
                await self._do_analyze_and_save(**job)
            except Exception as e:
                logger.error(
                    f"[{MEM_SYS}] | Task=分析触发 | worker 分析异常: session={session_id}, "
                    f"error={e}"
                )
            finally:
                queue.task_done()

    async def _do_analyze_and_save(
            self,
            namespace: str,
            session_id: str,
            speaker_id: str,
            audience: str,
            context_config: Optional[Dict] = None,
            buffered_snapshot: Optional[List[Dict[str, str]]] = None,
            user_id: str = "",
            round_id: int = 0,
            conversation_id: str = "",
    ) -> None:
        """
        实际执行分析并保存。由 worker 串行调用，保证：
        1. 每次分析时上一次的写入已完成
        2. 从内存缓存读取最新记忆（零 IO）
        """
        buffered = buffered_snapshot or self._message_buffer.get(session_id, [])
        if not buffered:
            return

        logger.debug(
            f"[{MEM_SYS}] | Task=分析触发 | 异步, round_id={round_id}, ns={namespace}, "
            f"user_id={user_id or '<空>'}, "
            f"buffer_size={len(buffered)}"
        )
        conversation_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in buffered
        )

        try:
            memories = await self._analyze_conversation(
                conversation_text, context_config, speaker_id,
                user_id=user_id,
                audiences=audience,
                session_id=session_id,
            )
            if memories:
                write_result = await self._save_memories_with_upsert(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    speaker_id=speaker_id,
                    audience=audience,
                    memories=memories,
                    user_id=user_id,
                    round_id=round_id,
                )
                if self._context_sync_processor is not None:
                    self._context_sync_processor.push_new_memories(memories)
                # 异步触发 embedding 后处理（不阻塞对话流）
                self._schedule_embedding(write_result)
            # 仅处理主 buffer 时更新索引；截断 snapshot 不能污染主 buffer 索引
            if buffered_snapshot is None:
                self._last_analyzed_index[session_id] = len(buffered)
        except Exception as e:
            logger.error(
                f"[{MEM_SYS}] | Task=分析触发 | 异步, round_id={round_id}, 分析异常: ns={namespace}, error={e}"
            )

    @property
    def sql_store(self) -> Optional[SQLStore]:
        return self._sql

    def set_context_sync_processor(self, processor: Any) -> None:
        """注入 ContextSyncProcessor，压缩完成后通知其刷新记忆缓存"""
        self._context_sync_processor = processor

    @property
    def has_sql_store(self) -> bool:
        return self._sql is not None

    @property
    def file_store(self) -> Optional[MemoryFileStore]:
        return self._file_store

    def _schedule_embedding(self, write_result: MemoryWriteResult) -> None:
        """
        异步触发 embedding 后处理（不阻塞对话流）。
        仅对 new_ids + updated_ids 生成 embedding。
        """
        if (
                self._embedding_service is None
                or not getattr(self._embedding_service, "enabled", False)
        ):
            return
        ids = write_result.ids_to_embed
        if not ids:
            return

        task = asyncio.create_task(
            self._embedding_service.process_memory_embeddings(ids)
        )
        # 持有强引用，防止 Task 被 GC 回收
        self._embedding_tasks.add(task)
        task.add_done_callback(self._embedding_tasks.discard)

    # ── 对外接口：每次收到消息时调用 ──
    async def on_message(
            self,
            namespace: str,
            session_id: str,
            speaker_id: str,
            audience: str,
            role: str,
            content: str,
            context_config: Optional[Dict] = None,
            user_id: str = "",
            conversation_id: str = "",
    ) -> None:
        """
        每条消息进入时调用，仅缓存到内存 buffer。
        记忆分析由截断触发（路径 B）和会话结束触发（路径 C）完成。
        """
        async with self._get_buffer_lock(session_id):
            if session_id not in self._message_buffer:
                self._message_buffer[session_id] = []
            if role == "user":
                self._round_counters[session_id] = self._round_counters.get(session_id, 0) + 1
            current_round = self._round_counters.get(session_id, 0)
            new_message = {
                "role": role,
                "content": content,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "round_id": current_round,
            }
            self._message_buffer[session_id].append(new_message)
            buffer_size = len(self._message_buffer[session_id])
            # 每条消息实时追加写入 MD 文件，在锁内调度确保写入顺序与 buffer 一致
            if self._file_store is not None:
                self._file_store.schedule_write_md(
                    user_id=user_id,
                    speaker_id=speaker_id,
                    session_id=session_id,
                    audiences=audience,
                    messages=[new_message],
                )
            if self._sql is not None and conversation_id:
                await self._sql.append_conversation_message(
                    conversation_id=conversation_id,
                    session_id=session_id,
                    user_id=user_id,
                    audiences=audience,
                    role=role,
                    content=content,
                    round_id=current_round,
                )

        logger.debug(
            f"[{MEM_SYS}] | Task=分析触发 | on_message: ns={namespace}, role={role}, "
            f"content_len={len(content)}, buffer_size={buffer_size}"
        )

    # ── 截断触发：ContextSyncProcessor 截断对话时调用 ──
    async def queue_truncated_messages(
            self,
            namespace: str,
            session_id: str,
            speaker_id: str,
            audience: str,
            messages: List[Dict[str, str]],
            context_config: Optional[Dict] = None,
            user_id: str = "",
            conversation_id: str = "",
    ) -> None:
        """
        将被截断丢弃的消息直接送入分析队列，提取摘要和事实，不浪费任何对话。
        由 ContextSyncProcessor 在截断对话时异步调用，不阻塞当前对话。

        安全过滤：丢弃开头缺少 user 上下文的孤立 assistant 消息，
        避免 LLM 在无上下文时将 assistant 的话错误归因为用户行为（Bug 3）。
        """
        if not messages:
            return

        # ── 过滤：丢弃开头孤立的 assistant 消息（缺少对应的 user 上下文）──
        cleaned = list(messages)
        while cleaned and cleaned[0].get("role") != "user":
            cleaned.pop(0)

        # 过滤后至少需要一条 user 消息，否则无法产生有意义的记忆
        has_user = any(m.get("role") == "user" for m in cleaned)
        if not cleaned or not has_user:
            logger.info(
                f"[{MEM_SYS}] | Task=分析排队 | 截断消息无有效 user 上下文，跳过分析: "
                f"ns={namespace}, 原始={len(messages)}条"
            )
            return

        # ── 补充 timestamp / round_id（截断消息来自 OpenAI 上下文，可能缺少这些字段）──
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inferred_round = 0
        for m in cleaned:
            if "timestamp" not in m:
                m["timestamp"] = now_ts
            if "round_id" not in m:
                if m.get("role") == "user":
                    inferred_round += 1
                m["round_id"] = inferred_round

        queue = self._get_analyze_queue(session_id)
        await queue.put({
            "namespace": namespace,
            "session_id": session_id,
            "speaker_id": speaker_id,
            "audience": audience,
            "context_config": context_config,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "buffered_snapshot": cleaned,
            "round_id": self._round_counters.get(session_id, 0),
        })
        self._ensure_worker(session_id)
        # 展示截断前后对比
        original_preview = [
            f"{m.get('role', '?')}: {truncate_content(m.get('content', ''), 40)}"
            for m in cleaned
        ]
        dropped = len(messages) - len(cleaned)
        logger.info(
            f"[{MEM_SYS}] | Task=分析排队 | 异步, round_id={self._round_counters.get(session_id, 0)}, "
            f"截断消息已送入分析队列: ns={namespace}, "
            f"截断={len(messages)}条, 过滤孤立assistant={dropped}条, "
            f"送入分析={len(cleaned)}条, "
            f"被截断内容={original_preview}"
        )

    # ── 被动记忆：用户说"帮我记一下XXX"时由 Tool 调用 ──
    async def analyze_and_save(
            self,
            namespace: str,
            session_id: str,
            speaker_id: str,
            audience: str,
            context_config: Optional[Dict] = None,
            user_id: str = "",
            conversation_id: str = "",
    ) -> str:
        """
        获取当前缓存的对话历史 → 调用 LLM 分析 → 写入 SQL。
        由 SaveEventTool / CompressSummaryTool 被动触发。
        ★ 先等待队列中所有待处理任务完成，再执行最终分析。
        """
        # 先等待队列排空（确保之前的分析全部完成）
        queue = self._get_analyze_queue(session_id)
        if not queue.empty():
            logger.info(
                f"[{MEM_SYS}] | Task=分析触发 | 等待队列排空: ns={namespace}"
            )
            await queue.join()

        async with self._get_buffer_lock(session_id):
            buffered = list(self._message_buffer.get(session_id, []))
            last_idx = self._last_analyzed_index.get(session_id, 0)

        if not buffered:
            return "当前没有对话记录"

        if len(buffered) <= last_idx:
            logger.info(
                f"[{MEM_SYS}] | Task=分析触发 | 无新消息，跳过重复分析: "
                f"ns={namespace}, buffer_len={len(buffered)}, last_analyzed={last_idx}"
            )
            return "当前没有新的对话记录需要分析"

        conversation_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in buffered
        )

        try:
            memories = await self._analyze_conversation(
                conversation_text, context_config, speaker_id,
                user_id=user_id,
                audiences=audience,
                session_id=session_id,
            )
            if memories:
                write_result = await self._save_memories_with_upsert(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    speaker_id=speaker_id,
                    audience=audience,
                    memories=memories,
                    user_id=user_id,
                    round_id=self._round_counters.get(session_id, 0),
                )
                # 记忆写入后直接推送到 ContextSync 缓存（不查询 DB），确保下轮上下文注入是最新数据
                if self._context_sync_processor is not None:
                    self._context_sync_processor.push_new_memories(memories)
                # 异步触发 embedding 后处理（不阻塞对话流）
                self._schedule_embedding(write_result)
                desc = "; ".join(
                    f"[{m.get('msg_type')}/{m.get('content_type')}] "
                    f"{flatten_content(m.get('contents', ''))}"
                    for m in memories
                )
                logger.info(
                    f"[{MEM_SYS}] | Task=事实写入 | analyze_and_save 完成: "
                    f"{len(memories)} 条记忆"
                )
                self._last_analyzed_index[session_id] = len(buffered)
                return f"已分析并保存 {len(memories)} 条记忆: {desc}"
            self._last_analyzed_index[session_id] = len(buffered)
            return "LLM 未从对话中提取到需要保存的记忆。"
        except Exception as e:
            logger.error(f"[{MEM_SYS}] | Task=事实写入 | analyze_and_save 异常: {e}")
            return f"分析保存失败: {e}"

    # ── 核心：先从内存读取已有记忆，再 1 次 LLM 调用统一分析（保持原有 prompt 不变） ──
    async def _analyze_conversation(
            self,
            conversation: str,
            config: Optional[Dict] = None,
            speaker_id: str = "",
            user_id: str = "",
            audiences: str = "",
            session_id: str = "",
    ) -> List[Dict[str, Any]]:
        """调用 LLM 分析对话，返回可持久化的记忆列表。"""
        existing_memories: List[Dict[str, Any]] = []
        existing_summaries: List[Dict[str, Any]] = []
        existing_facts: List[Dict[str, Any]] = []

        if self._file_store is not None:
            existing_memories = self._file_store.get_memories(
                audiences=audiences, user_id=user_id,
                speaker_id=speaker_id, session_id=session_id,
            )
            existing_summaries = self._file_store.get_summaries(
                audiences=audiences, user_id=user_id,
                speaker_id=speaker_id, session_id=session_id,
            )
            existing_facts = self._file_store.get_events(
                audiences=audiences, user_id=user_id,
                speaker_id=speaker_id, session_id=session_id,
            )

        logger.debug(
            f"[{MEM_SYS}] | Task=从内存读取数据 | "
            f"user_id={user_id}, speaker_id={speaker_id}, "
            f"session_id={session_id}, audiences={audiences or '无过滤'} "
            f"→已有记忆={len(existing_memories)}条; "
            f"摘要={len(existing_summaries)}条; "
            f"事实={len(existing_facts)}条"
        )

        memories_text = "(none)"
        if existing_memories:
            memory_lines = []
            for em in existing_memories:
                memory_lines.append(
                    f"  - id={em.get('id')}, contents={em.get('contents', '')!r}"
                )
            memories_text = "\n".join(memory_lines)

        context_parts = []
        if existing_summaries:
            summary_lines = "\n".join(
                f"[{s.get('create_time', '')}] {s.get('contents', '')}"
                for s in existing_summaries
            )
            context_parts.append(f"【对话摘要】\n{summary_lines}")
        if existing_facts:
            fact_lines = "\n".join(
                f"- [{e.get('content_type', '')}] {e.get('contents', '')} "
                f"(重要度:{e.get('importance', '')})"
                for e in existing_facts
            )
            context_parts.append(f"【重要事实】\n{fact_lines}")
        if context_parts:
            existing_context = "\n\n".join(context_parts)
            conversation = f"{existing_context}\n\n{conversation}"

        prompt = (
            "[SYSTEM] You are a memory writer, not a chatbot. "
            "Read only the existing memory text and the new conversation. "
            "Do not use predefined categories, relation vocabularies, keyword rules, "
            "or schema-specific interpretation. Preserve uncertainty in natural language.\n\n"
            f"Existing memories for speaker {speaker_id!r}:\n{memories_text}\n\n"
            "Return a JSON array only. Each item may contain these storage keys: "
            "contents, msg_type, content_type, importance, status. "
            f"Use msg_type={self._rules.summary_msg_type!r} only for a session summary; "
            f"use msg_type={self._rules.default_msg_type!r} for other memories. "
            "content_type is optional free text and may be empty. "
            "contents should be a natural-language statement or summary, not a forced triplet. "
            "Return [] when nothing should be stored."
        )
        user_content = (
            f"Conversation:\n{conversation}\n\n"
            "Output only the JSON array."
        )
        llm_messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ]
        logger.debug(
            f"[{MEM_SYS}] | Task=LLM分析请求 | "
            f"已有摘要={len(existing_summaries)}条, "
            f"已有事实={len(existing_facts)}条, "
            f"已有记忆={len(existing_memories)}条, "
            f"对话内容={flatten_content(conversation)}"
        )

        result = await self._llm_caller(messages=llm_messages)

        # 修改后：增加 JSON 提取 + 重试逻辑
        max_retries = 3
        last_error = None
        last_raw = result

        for attempt in range(max_retries + 1):
            try:
                text = last_raw.strip()

                # 尝试从文本中提取 JSON
                extracted = self._extract_json_from_text(text)
                if extracted:
                    text = extracted

                memories = json.loads(text)

                if isinstance(memories, list):
                    # ... 后续的 for m in memories 处理逻辑不变 ...
                    # （保持原有的 contents/action 归一化代码）
                    for m in memories:
                        if isinstance(m.get("contents"), dict):
                            m["contents"] = json.dumps(m["contents"], ensure_ascii=False)
                        if isinstance(m.get("invalid_contents"), dict):
                            m["invalid_contents"] = json.dumps(
                                m["invalid_contents"], ensure_ascii=False
                            )
                        if not m.get("msg_type"):
                            m["msg_type"] = self._rules.default_msg_type
                        if "content_type" not in m:
                            m["content_type"] = ""
                        if "importance" not in m:
                            m["importance"] = self._rules.default_importance
                        m["status"] = self._rules.valid_status

                    # 统计日志
                    details_str = "; ".join(
                        str(m.get("contents", "")) for m in memories
                    )
                    logger.info(
                        f"[{MEM_SYS}] | Task=LLM分析结果 | _analyze_conversation 完成: "
                        f"{len(memories)} 条记忆, 详情: {details_str}"
                        + (f" (重试第{attempt}次成功)" if attempt > 0 else "")
                        + f" | raw_output={flatten_content(result)}"
                    )
                    return memories

                # 返回的不是 list，当作解析失败处理
                last_error = f"返回类型为 {type(memories).__name__}，非 list"

            except (json.JSONDecodeError, TypeError) as e:
                last_error = e
                last_raw = result  # 保留原始响应用于日志

            # 重试：重新调用 LLM，prompt 中明确指出上次的错误
            if attempt < max_retries:
                logger.warning(
                    f"[{MEM_SYS}] | Task=LLM分析结果 | JSON解析失败(第{attempt + 1}次)，"
                    f"正在重试: error={last_error}"
                )
                retry_user_content = (
                    f"Conversation:\n{conversation}\n\n"
                    "Output only the JSON array."
                )
                retry_correction = (
                    "Your previous reply was not a valid JSON array. "
                    "Output only a JSON array [{...}, {...}] or []. "
                    "Do not include any other text."
                )
                try:
                    last_raw = await self._llm_caller(
                        messages=[
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": retry_user_content},
                            {"role": "assistant", "content": result},
                            {"role": "user", "content": retry_correction},
                        ],
                    )
                except Exception as retry_err:
                    logger.error(
                        f"[{MEM_SYS}] | Task=LLM分析请求 | 重试 LLM 调用失败: {retry_err}"
                    )
                    break

        # 所有重试都失败
        input_msg_count = len([
            ln for ln in conversation.splitlines() if ln.strip()
        ])
        logger.warning(
            f"[{MEM_SYS}] | Task=LLM分析结果 | JSON解析失败(已重试{max_retries}次): "
            f"input_msgs={input_msg_count}, "
            f"raw_response前100字='{result[:100]}', "
            f"error={last_error}"
        )
        return []

    # ── 会话结时强制分析保存 ──
    async def force_compress(
            self,
            namespace: str,
            session_id: str,
            speaker_id: str,
            audience: str,
            context_config: Optional[Dict] = None,
            user_id: str = "",
            conversation_id: str = "",
    ) -> None:
        """
        会话结束时调用：
        1. 等待队列中所有待处理的分析任务完成
        2. 执行最终一次全量分析保存
        3. 清理缓存和 worker
        """
        # Step 1: 等待队列排空
        queue = self._analyze_queues.get(session_id)
        if queue and not queue.empty():
            logger.info(
                f"[{MEM_SYS}] | Task=分析触发 | force_compress: 等待队列排空, ns={namespace}"
            )
            await queue.join()

        # Step 2: 执行最终一次分析保存
        result = await self.analyze_and_save(
            namespace=namespace,
            session_id=session_id,
            speaker_id=speaker_id,
            audience=audience,
            context_config=context_config,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        # Step 2.5: 确保断开时 {audiences}.json 始终覆盖写入最新缓存
        if self._file_store is not None:
            await self._file_store.flush_json(
                user_id=user_id,
                speaker_id=speaker_id,
                session_id=session_id,
                audiences=audience,
            )

        # Step 2.6: 将本次会话记忆同步写入 DB（供下次会话作为「过往」加载）
        if self._file_store is not None and self._sql is not None:
            try:
                await self._persist_session_memories_to_db(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    speaker_id=speaker_id,
                    session_id=session_id,
                    audiences=audience,
                )
            except Exception as e:
                logger.error(
                    f"[{MEM_SYS}] | Task=摘要写入 | 持久化记忆写入DB失败: ns={namespace}, error={e}"
                )

        # Step 3: 清理该 session 的所有资源
        async with self._get_buffer_lock(session_id):
            self._message_buffer.pop(session_id, None)
        self._buffer_locks.pop(session_id, None)
        self._analyze_queues.pop(session_id, None)
        self._last_analyzed_index.pop(session_id, None)
        self._round_counters.pop(session_id, None)
        # 取消 worker task
        worker = self._analyze_workers.pop(session_id, None)
        if worker and not worker.done():
            worker.cancel()
        logger.info(
            f"[{MEM_SYS}] | Task=摘要写入 | force_compress 完成: ns={namespace}, result={result}"
        )

        # Step 4: 通知 ContextSyncProcessor 刷新记忆缓存
        if self._context_sync_processor is not None:
            self._context_sync_processor.invalidate_memory_cache()

    async def _persist_session_memories_to_db(
            self,
            user_id: str,
            conversation_id: str,
            speaker_id: str,
            session_id: str,
            audiences: str,
    ) -> None:
        """
        将 file_store 缓存中的最终摘要和事实同步写入 DB。

        在 force_compress 完成后调用，确保本次会话记忆可被下次会话
        作为「过往摘要」/「过往事实」加载（通过 get_past_summaries/get_past_events）。

        摘要使用 upsert_summary（自带防重逻辑）；
        事实通过对比现有 contents 去重后再写入。
        """
        _summary_type = self._rules.summary_msg_type

        # 从 file_store 获取当前身份下的完整记忆（含 msg_type 等字段）
        memories = self._file_store.get_memories(
            audiences=audiences,
            user_id=user_id,
            speaker_id=speaker_id,
            session_id=session_id,
        )
        if not memories:
            logger.debug(
                f"[{MEM_SYS}] | Task=摘要写入 | 持久化到DB：file_store 无记忆，跳过: "
                f"session={session_id}, audiences={audiences}"
            )
            return

        summary_memories = [m for m in memories if m.get("msg_type") == _summary_type]
        event_memories = [m for m in memories if m.get("msg_type") != _summary_type]

        # ── 写入摘要（upsert 防重）──
        for sm in summary_memories:
            await self._sql.upsert_summary(
                session_id=session_id,
                speaker_id=speaker_id,
                audiences=audiences,
                summary=sm,
                user_id=user_id,
                conversation_id=conversation_id,
            )

        # ── 写入事实（查重后写入）──
        if event_memories:
            # 确定查询身份参数（复用 3 级策略）
            if user_id and speaker_id:
                q_user_id, q_speaker_id, q_session_id = user_id, speaker_id, ""
            elif user_id:
                q_user_id, q_speaker_id, q_session_id = user_id, "", ""
            else:
                q_user_id, q_speaker_id, q_session_id = "", "", session_id

            existing_events = await self._sql.get_events(
                audiences,
                user_id=q_user_id,
                speaker_id=q_speaker_id,
                session_id=q_session_id,
                limit=200,
            )
            existing_contents = {e.get("contents", "") for e in existing_events}

            new_events = [
                m for m in event_memories
                if m.get("contents", "") not in existing_contents
            ]
            if new_events:
                await self._sql.save_memories(
                    session_id=session_id,
                    speaker_id=speaker_id,
                    audiences=audiences,
                    memories=new_events,
                    user_id=user_id,
                    conversation_id=conversation_id,
                )

        logger.info(
            f"[{MEM_SYS}] | Task=摘要写入 | 持久化到DB完成: "
            f"session={session_id}, audiences={audiences}, "
            f"summaries={len(summary_memories)}条, "
            f"events={len(event_memories)}条"
        )

    async def _save_memories_with_upsert(
            self,
            session_id: str,
            conversation_id: str,
            speaker_id: str,
            audience: str,
            memories: List[Dict[str, Any]],
            user_id: str = "",
            round_id: int = 0,
    ) -> MemoryWriteResult:
        """
        保存记忆列表：更新内存缓存 + 异步落盘到文件。

        当 file_store 存在时走内存+文件链路；否则写入 DB。

        Returns:
            MemoryWriteResult: 区分 new_ids / updated_ids
        """
        result = MemoryWriteResult()

        # ── 内存+文件模式 ──
        if self._file_store is not None:
            _summary_type = self._rules.summary_msg_type

            self._file_store.update_memories(
                audiences=audience,
                user_id=user_id,
                speaker_id=speaker_id,
                session_id=session_id,
                memories=memories,
                summary_msg_type=_summary_type,
            )

            self._file_store.schedule_write_json(
                user_id=user_id,
                speaker_id=speaker_id,
                session_id=session_id,
                audiences=audience,
            )
            return result

        # ── DB 模式 ──
        return await self._save_memories_with_upsert_db(
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            audience=audience,
            memories=memories,
            user_id=user_id,
            round_id=round_id,
        )

    async def _save_memories_with_upsert_db(
            self,
            session_id: str,
            conversation_id: str,
            speaker_id: str,
            audience: str,
            memories: List[Dict[str, Any]],
            user_id: str = "",
            round_id: int = 0,
    ) -> MemoryWriteResult:
        """
        DB 链路保存记忆列表。

        处理优先级：conflict 最先 → add 其次 → keep 跳过

        Returns:
            MemoryWriteResult: 区分 new_ids / updated_ids
        """
        result = MemoryWriteResult()

        # ── 分离摘要和其他记忆 ──
        _summary_type = self._rules.summary_msg_type
        summary_memories = [m for m in memories if m.get("msg_type") == _summary_type]
        other_memories = [m for m in memories if m.get("msg_type") != _summary_type]

        # ── 摘要：upsert（摘要始终算 updated）──
        for sm in summary_memories:
            record_id = await self._sql.upsert_summary(
                session_id=session_id,
                speaker_id=speaker_id,
                audiences=audience,
                summary=sm,
                user_id=user_id,
                round_id=round_id,
                conversation_id=conversation_id,
            )
            result.updated_ids.append(record_id)

        if other_memories:
            new_ids = await self._sql.save_memories(
                session_id=session_id,
                speaker_id=speaker_id,
                audiences=audience,
                memories=other_memories,
                user_id=user_id,
                round_id=round_id,
                conversation_id=conversation_id,
            )
            result.new_ids.extend(new_ids)

        return result
