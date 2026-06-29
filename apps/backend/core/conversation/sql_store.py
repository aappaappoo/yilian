"""
SQL 存储层 — 对话记忆的统一 CRUD 操作

所有对话记忆（对话消息、摘要、事实、工具调用）统一存储到 conversation_memories 表。
contents 使用 TEXT（方便向量化），三元组放 metadata JSONB。
热度衰减公式：score = hot_values * 0.95^days
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_, func, update, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from loguru import logger

from core.conversation.knowledge import get_rules
from core.logging_utils import STARTUP, MEM_SYS
from core.conversation.models import (
    Conversation,
    ConversationMemory,
    ConversationMessage,
    ConversationSessionLink,
    compute_content_hash,
)


def _now() -> datetime:
    """当前本地时间，精确到秒"""
    return datetime.now().replace(microsecond=0)


class SQLStore:
    """
    SQL 持久存储，负责对话记忆的完整生命周期管理。
    """

    _TIME_FMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._rules = get_rules()
        logger.info(f"[{STARTUP}] | Task=SQLStore初始化 | SQLStore 初始化完成")

    @staticmethod
    def _default_title_from_message(content: str) -> str:
        title = (content or "").strip().replace("\n", " ")
        if not title:
            return "新对话"
        chars = list(title)
        return "".join(chars[:30]) + ("..." if len(chars) > 30 else "")

    async def create_conversation(
            self,
            *,
            user_id: str = "",
            audiences: str,
            conversation_id: str = "",
            title: str = "新对话",
            session_id: str = "",
            status: str = "active",
    ) -> Dict[str, Any]:
        """创建一个长期对话容器。conversation_id 可由前端传入，也可后端生成。"""
        cid = conversation_id or str(uuid.uuid4())
        now = _now()
        async with self._session_factory() as session:
            existing = (await session.execute(
                select(Conversation).where(Conversation.conversation_id == cid)
            )).scalar_one_or_none()
            if existing:
                if user_id and existing.user_id and existing.user_id != user_id:
                    raise ValueError("conversation_id 不属于当前用户")
                if not user_id and existing.user_id:
                    raise ValueError("conversation_id 不属于访客")
                return self._conversation_to_dict(existing)

            record = Conversation(
                conversation_id=cid,
                user_id=user_id or None,
                audiences=audiences,
                title=title.strip() or "新对话",
                preview="",
                status=status,
                last_session_id=session_id or None,
                message_count=0,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            if session_id:
                await self._link_session_in_tx(
                    session,
                    conversation_id=cid,
                    session_id=session_id,
                    user_id=user_id,
                    audiences=audiences,
                    now=now,
                )
            await session.commit()
            logger.info(
                f"[{MEM_SYS}] | Task=对话创建 | conversation={cid[:8]}, "
                f"user_id={user_id or 'NULL'}, audiences={audiences}, session={session_id[:8] if session_id else '<none>'}"
            )
            return self._conversation_to_dict(record)

    async def ensure_conversation(
            self,
            *,
            conversation_id: str,
            user_id: str = "",
            audiences: str,
            session_id: str = "",
            title: str = "新对话",
            status: str = "active",
    ) -> Dict[str, Any]:
        """确保 conversation 存在并关联 session_id。"""
        if not conversation_id:
            return await self.create_conversation(
                user_id=user_id,
                audiences=audiences,
                title=title,
                session_id=session_id,
                status=status,
            )

        now = _now()
        async with self._session_factory() as session:
            record = (await session.execute(
                select(Conversation).where(Conversation.conversation_id == conversation_id)
            )).scalar_one_or_none()
            if record is None:
                record = Conversation(
                    conversation_id=conversation_id,
                    user_id=user_id or None,
                    audiences=audiences,
                    title=title.strip() or "新对话",
                    preview="",
                    status=status,
                    last_session_id=session_id or None,
                    message_count=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                # 登录用户只能继续自己的 conversation；访客 conversation 不参与列表隔离。
                if user_id and record.user_id and record.user_id != user_id:
                    raise ValueError("conversation_id 不属于当前用户")
                if not user_id and record.user_id:
                    raise ValueError("conversation_id 不属于访客")
                if user_id and not record.user_id:
                    record.user_id = user_id
                if record.status == "deleted":
                    record.status = status
                record.audiences = audiences or record.audiences
                record.last_session_id = session_id or record.last_session_id
                record.updated_at = now

            if session_id:
                await self._link_session_in_tx(
                    session,
                    conversation_id=record.conversation_id,
                    session_id=session_id,
                    user_id=user_id,
                    audiences=audiences,
                    now=now,
                )
            await session.commit()
            return self._conversation_to_dict(record)

    async def list_conversations(
            self,
            *,
            user_id: str,
            audiences: str,
            limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if not user_id:
            return []
        async with self._session_factory() as session:
            stmt = (
                select(Conversation)
                .where(
                    and_(
                        Conversation.user_id == user_id,
                        Conversation.audiences == audiences,
                        Conversation.status == "active",
                    )
                )
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._conversation_to_dict(row) for row in result.scalars().all()]

    async def get_conversation(
            self,
            *,
            conversation_id: str,
            user_id: str,
    ) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            record = (await session.execute(
                select(Conversation).where(
                    and_(
                        Conversation.conversation_id == conversation_id,
                        Conversation.user_id == user_id,
                        Conversation.status == "active",
                    )
                )
            )).scalar_one_or_none()
            return self._conversation_to_dict(record) if record else None

    async def get_conversation_messages(
            self,
            *,
            conversation_id: str,
            user_id: str,
            limit: int = 200,
    ) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            stmt = (
                select(ConversationMessage)
                .where(
                    and_(
                        ConversationMessage.conversation_id == conversation_id,
                        ConversationMessage.user_id == user_id,
                        ConversationMessage.status == "active",
                    )
                )
                .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._message_to_dict(row) for row in result.scalars().all()]

    async def rename_conversation(self, *, conversation_id: str, user_id: str, title: str) -> bool:
        now = _now()
        async with self._session_factory() as session:
            result = await session.execute(
                update(Conversation)
                .where(
                    and_(
                        Conversation.conversation_id == conversation_id,
                        Conversation.user_id == user_id,
                        Conversation.status == "active",
                    )
                )
                .values(title=title.strip() or "新对话", updated_at=now)
            )
            await session.commit()
            return bool(result.rowcount)

    async def soft_delete_conversation(self, *, conversation_id: str, user_id: str) -> bool:
        now = _now()
        async with self._session_factory() as session:
            result = await session.execute(
                update(Conversation)
                .where(
                    and_(
                        Conversation.conversation_id == conversation_id,
                        Conversation.user_id == user_id,
                        Conversation.status != "deleted",
                    )
                )
                .values(status="deleted", updated_at=now)
            )
            await session.commit()
            return bool(result.rowcount)

    async def append_conversation_message(
            self,
            *,
            conversation_id: str,
            session_id: str,
            user_id: str = "",
            audiences: str,
            role: str,
            content: str,
            source: str = "",
            artifact: Optional[Dict[str, Any]] = None,
            round_id: Optional[int] = None,
    ) -> Optional[int]:
        if not conversation_id or not content.strip():
            return None
        now = _now()
        async with self._session_factory() as session:
            conversation = (await session.execute(
                select(Conversation).where(Conversation.conversation_id == conversation_id)
            )).scalar_one_or_none()
            if conversation is None:
                conversation = Conversation(
                    conversation_id=conversation_id,
                    user_id=user_id or None,
                    audiences=audiences,
                    title=self._default_title_from_message(content) if role == "user" else "新对话",
                    preview=content.strip(),
                    status="active" if user_id else "guest",
                    last_session_id=session_id,
                    message_count=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(conversation)
            elif user_id and conversation.user_id and conversation.user_id != user_id:
                raise ValueError("conversation_id 不属于当前用户")
            elif not user_id and conversation.user_id:
                raise ValueError("conversation_id 不属于访客")

            message = ConversationMessage(
                conversation_id=conversation_id,
                session_id=session_id,
                user_id=user_id or None,
                audiences=audiences,
                role=role,
                content=content,
                source=source or None,
                artifact=artifact,
                round_id=round_id,
                status="active",
                created_at=now,
            )
            session.add(message)
            await self._link_session_in_tx(
                session,
                conversation_id=conversation_id,
                session_id=session_id,
                user_id=user_id,
                audiences=audiences,
                now=now,
            )
            conversation.preview = content.strip()
            conversation.last_session_id = session_id
            conversation.message_count = (conversation.message_count or 0) + 1
            conversation.updated_at = now
            if role == "user" and (not conversation.title or conversation.title == "新对话"):
                conversation.title = self._default_title_from_message(content)
            await session.commit()
            return message.id

    async def _link_session_in_tx(
            self,
            session: AsyncSession,
            *,
            conversation_id: str,
            session_id: str,
            user_id: str,
            audiences: str,
            now: datetime,
    ) -> None:
        existing = (await session.execute(
            select(ConversationSessionLink).where(ConversationSessionLink.session_id == session_id)
        )).scalar_one_or_none()
        if existing:
            existing.conversation_id = conversation_id
            existing.user_id = user_id or None
            existing.audiences = audiences
            existing.last_seen_at = now
            return
        session.add(ConversationSessionLink(
            conversation_id=conversation_id,
            session_id=session_id,
            user_id=user_id or None,
            audiences=audiences,
            created_at=now,
            last_seen_at=now,
        ))

    @staticmethod
    def _conversation_to_dict(row: Conversation) -> Dict[str, Any]:
        return {
            "conversation_id": row.conversation_id,
            "user_id": row.user_id or "",
            "audiences": row.audiences,
            "title": row.title,
            "preview": row.preview or "",
            "status": row.status,
            "last_session_id": row.last_session_id or "",
            "message_count": row.message_count or 0,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }

    @staticmethod
    def _message_to_dict(row: ConversationMessage) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "conversation_id": row.conversation_id,
            "session_id": row.session_id,
            "role": row.role,
            "content": row.content,
            "source": row.source or "",
            "artifact": row.artifact,
            "round_id": row.round_id,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }

    async def soft_delete_session(self, session_id: str) -> int:
        """
        Soft-delete all persisted memory rows for a conversation session.

        Rows are kept in the database for audit/recovery, but normal queries
        ignore them because they no longer have the valid status.
        """
        if not session_id:
            return 0
        now = _now()
        async with self._session_factory() as session:
            result = await session.execute(
                update(ConversationMemory)
                .where(
                    ConversationMemory.session_id == session_id,
                    ConversationMemory.status != "deleted",
                )
                .values(status="deleted", updated_at=now)
            )
            await session.commit()
            count = result.rowcount or 0
        logger.info(
            f"[{MEM_SYS}] | Task=会话软删除 | table=conversation_memories, "
            f"session={session_id[:8]}, affected={count}"
        )
        return count

    # ── 查询方法 ──

    async def get_messages(
            self,
            session_id: str,
            speaker_id: Optional[str] = None,
            msg_type: Optional[str] = None,
            limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        获取指定 session 的消息列表。
        """
        async with self._session_factory() as session:
            conditions = [
                ConversationMemory.session_id == session_id,
                ConversationMemory.status == self._rules.valid_status,
            ]
            if speaker_id:
                conditions.append(ConversationMemory.speaker_id == speaker_id)
            if msg_type:
                conditions.append(ConversationMemory.msg_type == msg_type)

            stmt = (
                select(ConversationMemory)
                .where(and_(*conditions))
                .order_by(ConversationMemory.create_time.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [self._row_to_dict(r) for r in rows]

    async def get_summaries(
            self,
            audiences: str,
            user_id: str = "",
            speaker_id: str = "",
            session_id: str = "",
            limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        获取指定 audiences 的对话摘要，支持 3 级身份查询。

        查询策略（按优先级）：
        1. 未登录：仅用 session_id + audiences 查询
        2. 已登录 + speaker_id 不存在：仅用 user_id + audiences 查询
        3. 已登录 + speaker_id 存在：仅用 speaker_id + audiences 查询（多用户精确匹配）

        返回格式: [{"create_time": "...", "contents": "..."}, ...]
        """
        base_conditions = [
            ConversationMemory.audiences == audiences,
            ConversationMemory.msg_type == self._rules.summary_msg_type,
            ConversationMemory.status == self._rules.valid_status,
        ]

        # ── 3 级身份查询 ──
        if user_id and speaker_id:
            # 场景 3：已登录 + speaker_id 存在 → 仅用 speaker_id（多用户精确匹配）
            identity_conditions = [ConversationMemory.speaker_id == speaker_id]
            identity_desc = f"speaker_id={speaker_id}"
        elif user_id:
            # 场景 2：已登录 + 无 speaker_id → 仅用 user_id
            identity_conditions = [ConversationMemory.user_id == user_id]
            identity_desc = f"user_id={user_id}"
        elif session_id:
            # 场景 1：未登录 → 仅用 session_id
            identity_conditions = [ConversationMemory.session_id == session_id]
            identity_desc = f"session_id={session_id}"
        else:
            # 无任何身份标识：返回全部（供管理/调试脚本使用）
            async with self._session_factory() as session:
                stmt = (
                    select(ConversationMemory)
                    .where(and_(*base_conditions))
                    .order_by(ConversationMemory.create_time.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [self._row_to_dict(r) for r in rows]

        async with self._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(and_(*(base_conditions + identity_conditions)))
                .order_by(ConversationMemory.create_time.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            logger.debug(
                f"[{MEM_SYS}] | Task=DB查询记忆 | get_summaries: audiences={audiences}, "
                f"{identity_desc}, 结果={len(rows)}条"
            )
            return [self._row_to_dict(r) for r in rows]

    async def get_events(
            self,
            audiences: str,
            user_id: str = "",
            speaker_id: str = "",
            session_id: str = "",
            limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        获取指定 audiences 的重要事件/事实记忆，支持 3 级身份查询。

        查询策略（按优先级）：
        1. 未登录：仅用 session_id + audiences 查询
        2. 已登录 + speaker_id 不存在：仅用 user_id + audiences 查询
        3. 已登录 + speaker_id 存在：仅用 speaker_id + audiences 查询（多用户精确匹配）

        返回格式: [{"content_type": "...", "contents": "...", "importance": N}, ...]
        """
        base_conditions = [
            ConversationMemory.audiences == audiences,
            ConversationMemory.msg_type == self._rules.default_msg_type,
            ConversationMemory.status == self._rules.valid_status,
        ]

        # ── 3 级身份查询 ──
        if user_id and speaker_id:
            # 场景 3：已登录 + speaker_id 存在 → 仅用 speaker_id（多用户精确匹配）
            identity_conditions = [ConversationMemory.speaker_id == speaker_id]
            identity_desc = f"speaker_id={speaker_id}"
        elif user_id:
            # 场景 2：已登录 + 无 speaker_id → 仅用 user_id
            identity_conditions = [ConversationMemory.user_id == user_id]
            identity_desc = f"user_id={user_id}"
        elif session_id:
            # 场景 1：未登录 → 仅用 session_id
            identity_conditions = [ConversationMemory.session_id == session_id]
            identity_desc = f"session_id={session_id}"
        else:
            logger.warning(
                f"[{MEM_SYS}] | Task=DB查询记忆 | get_events 缺少所有身份标识，跳过查询: "
                f"audiences={audiences}"
            )
            return []

        async with self._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(and_(*(base_conditions + identity_conditions)))
                .order_by(ConversationMemory.importance.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            logger.debug(
                f"[{MEM_SYS}] | Task=DB查询记忆 | get_events: audiences={audiences}, "
                f"{identity_desc}, 结果={len(rows)}条"
            )
            return [self._row_to_dict(r) for r in rows]

    async def get_past_summaries(
            self,
            audiences: str,
            user_id: str = "",
            speaker_id: str = "",
            session_id: str = "",
            limit: int = 5,
            since_days: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        获取指定 audiences 最近 since_days 天内的对话摘要（过往层），支持 3 级身份查询。

        与 get_summaries() 相同，但增加 updated_at 时间过滤（仅返回最近 5 天的数据）。
        """
        cutoff = datetime.now() - timedelta(days=since_days)

        base_conditions = [
            ConversationMemory.audiences == audiences,
            ConversationMemory.msg_type == self._rules.summary_msg_type,
            ConversationMemory.status == self._rules.valid_status,
            ConversationMemory.updated_at >= cutoff,
        ]

        if user_id and speaker_id:
            identity_conditions = [ConversationMemory.speaker_id == speaker_id]
            identity_desc = f"speaker_id={speaker_id}"
        elif user_id:
            identity_conditions = [ConversationMemory.user_id == user_id]
            identity_desc = f"user_id={user_id}"
        elif session_id:
            identity_conditions = [ConversationMemory.session_id == session_id]
            identity_desc = f"session_id={session_id}"
        else:
            logger.warning(
                f"[{MEM_SYS}] | Task=DB查询过往记忆 | get_past_summaries 缺少所有身份标识，跳过查询: "
                f"audiences={audiences}"
            )
            return []

        async with self._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(and_(*(base_conditions + identity_conditions)))
                .order_by(ConversationMemory.create_time.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            logger.debug(
                f"[{MEM_SYS}] | Task=DB查询过往记忆 | get_past_summaries: audiences={audiences}, "
                f"{identity_desc}, since_days={since_days}, 结果={len(rows)}条"
            )
            return [self._row_to_dict(r) for r in rows]

    async def get_past_events(
            self,
            audiences: str,
            user_id: str = "",
            speaker_id: str = "",
            session_id: str = "",
            limit: int = 20,
            since_days: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        获取指定 audiences 最近 since_days 天内的事实记忆（过往层），支持 3 级身份查询。

        与 get_events() 相同，但增加 updated_at 时间过滤（仅返回最近 5 天的数据）。
        """
        cutoff = datetime.now() - timedelta(days=since_days)

        base_conditions = [
            ConversationMemory.audiences == audiences,
            ConversationMemory.msg_type == self._rules.default_msg_type,
            ConversationMemory.status == self._rules.valid_status,
            ConversationMemory.updated_at >= cutoff,
        ]

        if user_id and speaker_id:
            identity_conditions = [ConversationMemory.speaker_id == speaker_id]
            identity_desc = f"speaker_id={speaker_id}"
        elif user_id:
            identity_conditions = [ConversationMemory.user_id == user_id]
            identity_desc = f"user_id={user_id}"
        elif session_id:
            identity_conditions = [ConversationMemory.session_id == session_id]
            identity_desc = f"session_id={session_id}"
        else:
            logger.warning(
                f"[{MEM_SYS}] | Task=DB查询过往记忆 | get_past_events 缺少所有身份标识，跳过查询: "
                f"audiences={audiences}"
            )
            return []

        async with self._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(and_(*(base_conditions + identity_conditions)))
                .order_by(ConversationMemory.importance.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            logger.debug(
                f"[{MEM_SYS}] | Task=DB查询过往记忆 | get_past_events: audiences={audiences}, "
                f"{identity_desc}, since_days={since_days}, 结果={len(rows)}条"
            )
            return [self._row_to_dict(r) for r in rows]

    async def get_recent_dialogue(
            self,
            session_id: str,
            limit: int = 30,
    ) -> List[Dict[str, str]]:
        """
        获取最近的对话消息。
        返回格式: [{"role": "user", "content": "..."}]
        注：role 从 content_type 字段读取，若为空则默认 "user"
        """
        async with self._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(
                    and_(
                        ConversationMemory.session_id == session_id,
                        ConversationMemory.msg_type == "对话",
                        ConversationMemory.status == self._rules.valid_status,
                    )
                )
                .order_by(ConversationMemory.create_time.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {"role": r.content_type or "user", "content": r.contents}
                for r in rows
            ]

    async def get_speaker_memories(
            self,
            speaker_id: str,
            status: str = "valid",
            limit: int = 100,
            user_id: str = "",
            audiences: str = "",
            session_id: str = "",
    ) -> List[Dict[str, Any]]:
        """
        获取指定身份下指定状态的所有记忆记录，支持 4 级身份查询。
        用于在 LLM 分析前提供已有记忆上下文。

        查询策略：
        1. user_id 非空时：user_id + speaker_id 联合查询（已认证用户）
        2. user_id 为空、speaker_id 非空时：按 speaker_id 查询
        3. user_id 和 speaker_id 均为空、session_id 非空时：按 session_id + audiences 查询（未认证）
        4. 三者均为空时：返回空列表

        Args:
            audiences: 非空时加入查询条件做 audience 隔离；空时不过滤。
            session_id: 未认证时按 session_id 查询记忆。
        """
        base_conditions = [
            ConversationMemory.status == status,
            ConversationMemory.msg_type != self._rules.summary_msg_type,
        ]
        if audiences:
            base_conditions.append(ConversationMemory.audiences == audiences)

        where_desc = (
            f"user_id={user_id}, speaker_id={speaker_id}, "
            f"session_id={session_id}, "
            f"audiences={audiences or '无过滤'}, status={status}"
        )

        if user_id:
            # user_id 为主键 + speaker_id 为辅助
            identity_conditions = [ConversationMemory.user_id == user_id]
            if speaker_id:
                identity_conditions.append(ConversationMemory.speaker_id == speaker_id)

            async with self._session_factory() as session:
                stmt = (
                    select(ConversationMemory)
                    .where(and_(*(base_conditions + identity_conditions)))
                    .order_by(ConversationMemory.updated_at.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                if rows:
                    return [self._row_to_dict(r) for r in rows]
            return []

        # user_id 为空时按 speaker_id 查询
        if speaker_id:
            async with self._session_factory() as session:
                stmt = (
                    select(ConversationMemory)
                    .where(
                        and_(
                            ConversationMemory.speaker_id == speaker_id,
                            *base_conditions,
                        )
                    )
                    .order_by(ConversationMemory.updated_at.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [self._row_to_dict(r) for r in rows]

        # user_id 和 speaker_id 均为空，按 session_id 查询（未认证）
        if session_id:
            async with self._session_factory() as session:
                stmt = (
                    select(ConversationMemory)
                    .where(
                        and_(
                            ConversationMemory.session_id == session_id,
                            *base_conditions,
                        )
                    )
                    .order_by(ConversationMemory.updated_at.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [self._row_to_dict(r) for r in rows]

        return []

    # ── 写入 / 更新方法 ──
    async def save_memories(
            self,
            session_id: str,
            speaker_id: str,
            audiences: str,
            memories: List[Dict[str, Any]],
            user_id: str = "",
            round_id: Optional[int] = None,
            conversation_id: str = "",
    ) -> List[int]:
        """
        批量写入 LLM 分析产生的记忆条目。
        每条 memory 必须包含: contents, msg_type, content_type, importance
        新记录 status 默认为 valid。
        """
        if not memories:
            return []
        now = _now()
        if not user_id:
            logger.warning(
                f"[{MEM_SYS}] | Task=数据校验 | save_memories: user_id 为空，记录将以 NULL 写入数据库: "
                f"session={session_id}, speaker={speaker_id}, audiences={audiences}"
            )
        async with self._session_factory() as session:
            records = []
            for m in memories:
                contents = m.get("contents")
                c_hash = compute_content_hash(contents) if contents else None
                record = ConversationMemory(
                    conversation_id=conversation_id or None,
                    session_id=session_id,
                    audiences=audiences,
                    speaker_id=speaker_id,
                    user_id=user_id or None,
                    contents=contents,
                    content_hash=c_hash,
                    msg_type=m.get("msg_type"),
                    content_type=m.get("content_type"),
                    importance=m.get("importance"),
                    status=self._rules.valid_status,
                    create_time=now,
                    updated_at=now,
                    last_accessed_at=now,
                    round_id=round_id,
                )
                session.add(record)
                records.append(record)
            await session.commit()
            ids = [r.id for r in records]
            logger.info(
                f"[{MEM_SYS}] | Task=事实写入 | save_memories: table=conversation_memories, "
                f"写入条件=[session_id={session_id}, audiences={audiences}, "
                f"speaker_id={speaker_id}, user_id={user_id or 'NULL'}], count={len(ids)}"
            )
            return ids

    async def update_memory_content(
            self,
            record_id: int,
            contents: str,
            importance: Optional[int] = None,
    ) -> None:
        """
        更新指定记忆 contents 和 updated_at（不修改 create_time）。
        用于 expand（扩展/合并）操作 — 用合并后的数据替换原记录。
        """
        now = _now()
        async with self._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(ConversationMemory.id == record_id)
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                record.contents = contents
                record.content_hash = compute_content_hash(contents)
                record.updated_at = now
                record.last_accessed_at = now
                if importance is not None:
                    record.importance = importance
                await session.commit()
                logger.info(
                    f"[{MEM_SYS}] | Task=事实写入 | 记忆已更新(expand替换): id={record_id}, "
                    f"updated_at={now}"
                )
            else:
                logger.warning(f"[{MEM_SYS}] | Task=事实写入 | 更新失败，记录不存在: id={record_id}")

    # ── 热度衰减计算 ──
    def calculate_hot_score(self, hot_values: int, last_accessed_at: datetime) -> float:
        """
        计算热度得分。

        公式: score = hot_values * 0.95^days
        其中 days 是距离最后访问时间的天数。

        示例: 2 天后 hot_values=100 → 100 * 0.95^2 = 90.25
        """
        now = datetime.now(timezone.utc)
        if last_accessed_at.tzinfo is None:
            from datetime import timezone as tz
            last_accessed_at = last_accessed_at.replace(tzinfo=tz.utc)
        delta = now - last_accessed_at
        days = delta.total_seconds() / 86400.0
        return hot_values * (0.95 ** days)

    # ── 内部工具方法 ──
    @staticmethod
    def _row_to_dict(r: ConversationMemory) -> Dict[str, Any]:
        fmt = SQLStore._TIME_FMT
        return {
            "id": r.id,
            "session_id": r.session_id,
            "audiences": r.audiences,
            "speaker_id": r.speaker_id,
            "user_id": r.user_id,
            "create_time": r.create_time.strftime(fmt),
            "updated_at": r.updated_at.strftime(fmt),
            "status": r.status,
            "contents": r.contents,
            "content_hash": r.content_hash,
            "msg_type": r.msg_type,
            "content_type": r.content_type,
            "importance": r.importance,
            "hot_values": r.hot_values,
            "last_accessed_at": r.last_accessed_at.strftime(fmt),
        }

    async def get_message_count(
            self,
            session_id: str,
            msg_type: Optional[str] = None,
    ) -> int:
        """获取指定 session 的消息数量。"""
        async with self._session_factory() as session:
            conditions = [
                ConversationMemory.session_id == session_id,
                ConversationMemory.status == self._rules.valid_status,
            ]
            if msg_type:
                conditions.append(ConversationMemory.msg_type == msg_type)

            stmt = select(func.count(ConversationMemory.id)).where(and_(*conditions))
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def upsert_summary(
            self,
            session_id: str,
            speaker_id: str,
            audiences: str,
            summary: Dict[str, Any],
            user_id: str = "",
            round_id: Optional[int] = None,
            conversation_id: str = "",
    ) -> int:
        """
        插入或更新摘要记录。
        先查询该 audiences 下是否已存在 msg_type='对话摘要' 的记录：
        - 如果存在：更新 contents、importance、updated_at
        - 如果不存在：插入新记录

        Returns:
            int: 记录 ID
        """
        now = _now()
        if not user_id:
            logger.warning(
                f"[{MEM_SYS}] | Task=数据校验 | upsert_summary: user_id 为空，摘要记录将以 NULL 写入数据库: "
                f"session={session_id}, speaker={speaker_id}, audiences={audiences}"
            )
        async with self._session_factory() as session:
            # 按 user_id 精确过滤，防止错误更新其他用户的摘要。
            # with_for_update() 加行级锁，避免并发修改导致数据冲突。
            identity_conditions = []
            if user_id:
                identity_conditions.append(ConversationMemory.user_id == user_id)
            elif conversation_id:
                identity_conditions.append(ConversationMemory.conversation_id == conversation_id)
            elif session_id:
                identity_conditions.append(ConversationMemory.session_id == session_id)
            stmt = (
                select(ConversationMemory)
                .where(
                    and_(
                        ConversationMemory.audiences == audiences,
                        ConversationMemory.msg_type == self._rules.summary_msg_type,
                        ConversationMemory.status == self._rules.valid_status,
                        *identity_conditions,
                    )
                )
                .order_by(ConversationMemory.create_time.desc())
                .limit(1)
                .with_for_update()
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                old_contents = existing.contents
                new_contents = summary.get("contents", existing.contents)
                existing.contents = new_contents
                existing.importance = summary.get("importance", existing.importance)
                existing.content_type = summary.get("content_type", existing.content_type)
                existing.conversation_id = conversation_id or existing.conversation_id
                existing.updated_at = now
                existing.last_accessed_at = now
                await session.commit()
                logger.debug(
                    f"[{MEM_SYS}] | Task=摘要写入 | upsert_summary: UPDATE id={existing.id}, "
                    f"session_id={session_id}, user_id={user_id}, speaker_id={speaker_id}, audiences={audiences}, "
                    f"contents: '{old_contents}' → '{new_contents}'"
                )
                return existing.id
            else:
                record = ConversationMemory(
                    conversation_id=conversation_id or None,
                    session_id=session_id,
                    audiences=audiences,
                    speaker_id=speaker_id,
                    user_id=user_id or None,
                    contents=summary.get("contents"),
                    msg_type=summary.get("msg_type", self._rules.summary_msg_type),
                    content_type=summary.get("content_type"),
                    importance=summary.get("importance"),
                    status=self._rules.valid_status,
                    create_time=now,
                    updated_at=now,
                    last_accessed_at=now,
                    round_id=round_id,
                )
                session.add(record)
                await session.commit()
                logger.debug(
                    f"[{MEM_SYS}] | Task=摘要写入 | upsert_summary: INSERT new id={record.id}, "
                    f"session_id={session_id}, user_id={user_id}, speaker_id={speaker_id}, audiences={audiences}"
                )
                return record.id

    async def upsert_compress_summary(
            self,
            session_id: str,
            summary_text: str,
    ) -> int:
        """
        插入或更新本轮压缩摘要记录。
        按 session_id + msg_type='本轮压缩摘要' 做 upsert（一个 session 只保留一条）。

        Returns:
            int: 记录 ID
        """
        now = _now()
        compress_msg_type = self._rules.compress_summary_msg_type
        async with self._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(
                    and_(
                        ConversationMemory.session_id == session_id,
                        ConversationMemory.msg_type == compress_msg_type,
                        ConversationMemory.status == self._rules.valid_status,
                    )
                )
                .order_by(ConversationMemory.create_time.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                old_contents = existing.contents or ""
                existing.contents = summary_text
                existing.content_hash = compute_content_hash(summary_text)
                existing.updated_at = now
                existing.last_accessed_at = now
                await session.commit()
                logger.debug(
                    f"[{MEM_SYS}] | Task=压缩摘要生成 | upsert_compress_summary: UPDATE id={existing.id}, "
                    f"session={session_id}, "
                    f"contents: '{old_contents[:60]}' → '{summary_text[:60]}'"
                )
                return existing.id
            else:
                record = ConversationMemory(
                    session_id=session_id,
                    audiences="",
                    speaker_id="",
                    user_id=None,
                    contents=summary_text,
                    content_hash=compute_content_hash(summary_text),
                    msg_type=compress_msg_type,
                    content_type="",
                    importance=5,
                    status=self._rules.valid_status,
                    create_time=now,
                    updated_at=now,
                    last_accessed_at=now,
                )
                session.add(record)
                await session.commit()
                logger.debug(
                    f"[{MEM_SYS}] | Task=压缩摘要生成 | upsert_compress_summary: INSERT new id={record.id}, "
                    f"session={session_id}"
                )
                return record.id

    async def get_compress_summary(
            self,
            session_id: str,
    ) -> Optional[str]:
        """
        查询指定 session 的本轮压缩摘要文本。

        Returns:
            Optional[str]: 摘要文本，不存在时返回 None
        """
        compress_msg_type = self._rules.compress_summary_msg_type
        async with self._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(
                    and_(
                        ConversationMemory.session_id == session_id,
                        ConversationMemory.msg_type == compress_msg_type,
                        ConversationMemory.status == self._rules.valid_status,
                    )
                )
                .order_by(ConversationMemory.updated_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            return record.contents if record else None

    async def get_memory_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """按 id 查询单条记忆记录。"""
        async with self._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(ConversationMemory.id == record_id)
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                return self._row_to_dict(record)
            return None

    # ── Embedding 相关方法 ──

    async def get_memories_by_ids(
            self,
            record_ids: List[int],
    ) -> List[Dict[str, Any]]:
        """
        按 id 批量读取记忆记录的 contents，供 embedding 服务使用。
        """
        if not record_ids:
            return []
        async with self._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(ConversationMemory.id.in_(record_ids))
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._row_to_dict(r) for r in rows]

    async def batch_save_embeddings(
            self,
            id_embedding_pairs: List[tuple],
    ) -> int:
        """
        批量将 embedding 向量写入 embedding 列。

        Args:
            id_embedding_pairs: [(record_id, embedding_vector_str), ...]
                embedding_vector_str 为 pgvector 兼容的格式，如 "[0.1, 0.2, ...]"

        Returns:
            int: 成功写入的记录数
        """
        if not id_embedding_pairs:
            return 0
        count = 0
        async with self._session_factory() as session:
            for record_id, emb_str in id_embedding_pairs:
                try:
                    await session.execute(
                        sa_text(
                            "UPDATE conversation_memories "
                            "SET embedding = :emb WHERE id = :rid"
                        ),
                        {"emb": emb_str, "rid": record_id},
                    )
                    count += 1
                except Exception as e:
                    logger.warning(
                        f"[{MEM_SYS}] | Task=事实写入 | batch_save_embeddings: id={record_id} 写入失败: {e}"
                    )
            await session.commit()
        return count

    async def search_by_embedding(
            self,
            query_vector: str,
            speaker_id: str,
            top_k: int = 10,
            similarity_weight: float = 0.6,
            hot_decay_weight: float = 0.4,
    ) -> List[Dict[str, Any]]:
        """
        语义检索：用 pgvector 的余弦距离做向量检索，
        并与热度衰减打分融合排序。

        融合公式:
            final_score = similarity_weight * cosine_similarity
                        + hot_decay_weight * normalized_hot_score

        其中 normalized_hot_score = hot_values * 0.95^days / max_hot_score

        Args:
            query_vector: 查询向量（pgvector 格式字符串，如 "[0.1, 0.2, ...]"）
            speaker_id: 说话者 ID
            top_k: 返回前 K 条
            similarity_weight: 语义相似度权重
            hot_decay_weight: 热度衰减权重

        Returns:
            List[Dict]: 融合排序后的记忆列表，每条包含 similarity_score 和 hot_score
        """
        async with self._session_factory() as session:
            # pgvector cosine distance: 1 - cosine_similarity
            # 先用 pgvector 做粗筛（取 top_k * 3 保证融合后有足够候选）
            candidate_limit = top_k * 3
            stmt = sa_text(
                "SELECT id, session_id, audiences, speaker_id, "
                "create_time, updated_at, status, contents, content_hash, "
                "msg_type, content_type, importance, hot_values, "
                "last_accessed_at, "
                "1 - (embedding <=> :qvec) AS similarity "
                "FROM conversation_memories "
                "WHERE speaker_id = :sid "
                "AND status = :valid_status "
                "AND embedding IS NOT NULL "
                "ORDER BY embedding <=> :qvec "
                "LIMIT :lim"
            )
            result = await session.execute(stmt, {
                "qvec": query_vector,
                "sid": speaker_id,
                "valid_status": self._rules.valid_status,
                "lim": candidate_limit,
            })
            rows = result.fetchall()

            if not rows:
                return []

            # 计算热度衰减并融合排序
            from datetime import timezone as tz
            now = datetime.now(tz.utc)
            candidates = []
            max_hot_score = 0.0

            for row in rows:
                hot_values = row.hot_values or 0
                last_accessed = row.last_accessed_at
                if last_accessed and last_accessed.tzinfo is None:
                    last_accessed = last_accessed.replace(tzinfo=tz.utc)
                days = (now - last_accessed).total_seconds() / 86400.0 if last_accessed else 0.0
                hot_score = hot_values * (0.95 ** days)
                max_hot_score = max(max_hot_score, hot_score)
                candidates.append({
                    "id": row.id,
                    "session_id": row.session_id,
                    "audiences": row.audiences,
                    "speaker_id": row.speaker_id,
                    "create_time": row.create_time.strftime(self._TIME_FMT) if row.create_time else None,
                    "updated_at": row.updated_at.strftime(self._TIME_FMT) if row.updated_at else None,
                    "status": row.status,
                    "contents": row.contents,
                    "content_hash": row.content_hash,
                    "msg_type": row.msg_type,
                    "content_type": row.content_type,
                    "importance": row.importance,
                    "hot_values": row.hot_values,
                    "last_accessed_at": row.last_accessed_at.strftime(self._TIME_FMT) if row.last_accessed_at else None,
                    "similarity_score": float(row.similarity),
                    "hot_score": hot_score,
                })

            # 归一化热度分数并计算融合分
            for c in candidates:
                norm_hot = c["hot_score"] / max_hot_score if max_hot_score > 0 else 0.0
                c["final_score"] = (
                        similarity_weight * c["similarity_score"]
                        + hot_decay_weight * norm_hot
                )

            # 按融合分降序排序
            candidates.sort(key=lambda x: x["final_score"], reverse=True)
            return candidates[:top_k]
