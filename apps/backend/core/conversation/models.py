"""
SQL 数据库模型

conversation_memories: 对话记忆统一表
  - 每一轮对话记忆都保存到 PostgreSQL
  - contents 使用 TEXT（方便向量化）
  - metadata 使用 JSONB（存放三元组等结构化数据）
  - 向量化使用 pgvector

支持 PostgreSQL (生产) 和 SQLite (开发)
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

from sqlalchemy import (
    Column, String, Text, Integer, Float, DateTime, Index,
    text as sa_text,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from loguru import logger
from core.logging_utils import STARTUP, MEM_SYS


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    """返回不带时区、不带微秒的当前时间（本地时间）"""
    return datetime.now().replace(microsecond=0)


def compute_content_hash(contents: str) -> str:
    """
    计算 contents 的 md5 hash，用于写前快速去重。
    对 JSON 做 sort_keys=True + 对 object 数组排序，保证语义等价的内容产生相同 hash。
    """
    try:
        data = json.loads(contents)
        if isinstance(data, dict):
            # 对 object 数组排序（如果存在且为列表）
            if "object" in data and isinstance(data["object"], list):
                data["object"] = sorted(data["object"])
            normalized = json.dumps(data, sort_keys=True, ensure_ascii=False)
        else:
            normalized = contents
    except (json.JSONDecodeError, TypeError):
        normalized = contents
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


@dataclass
class MemoryWriteResult:
    """_save_memories_with_upsert 的写入结果。"""

    new_ids: List[int] = field(default_factory=list)
    updated_ids: List[int] = field(default_factory=list)

    @property
    def ids_to_embed(self) -> List[int]:
        return self.new_ids + self.updated_ids

    @property
    def all_ids(self) -> List[int]:
        return self.ids_to_embed


class ConversationMemory(Base):
    """
    增加日志打印，方便调试
    """
    __tablename__ = "conversation_memories"

    # 添加字段声明
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(128), nullable=True, index=True, comment="长期对话容器 ID")
    session_id = Column(String(128), nullable=False, index=True)
    audiences = Column(String(64), nullable=False, comment="人群标识")
    speaker_id = Column(String(128), nullable=False, index=True)
    user_id = Column(String(128), nullable=True, index=True, comment="鉴权后的用户唯一标识")
    create_time = Column(DateTime, default=_utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, comment="更新时间")
    status = Column(String(32), default="valid", comment="状态: valid / invalid")
    contents = Column(Text, nullable=False, comment="内容文本或元数据，如三元组 {subject, relation, object}")
    content_hash = Column(String(32), nullable=True, index=True, comment="contents 的 MD5 hash，用于写前快速去重")
    msg_type = Column(String(32), nullable=False, comment="消息类型: 摘要 / 元数据 / 工具调用 / 主体")
    content_type = Column(String(64), nullable=True, comment="内容类别")
    importance = Column(Integer, default=3, comment="重要程度 1-5；结合人设自行判断")
    hot_values = Column(Integer, default=0, comment="热度值（被调用/访问次数）")
    last_accessed_at = Column(DateTime, default=_utcnow, comment="最后访问时间")
    round_id = Column(Integer, nullable=True, comment="对话轮次ID，记录该条记忆来自哪一轮对话")

    def __repr__(self) -> str:
        return (
            f"<Memory id={self.id} session={self.session_id} "
            f"msg_type={self.msg_type} importance={self.importance}>"
        )

    def log_memory_entry(self):
        """日志打印当前内存条目信息，便于调试"""
        logger.info(
            f"[ConversationMemory] "
            f"ID: {self.id}, SessionID: {self.session_id}, "
            f"SpeakerID: {self.speaker_id}, MSG_TYPE: {self.msg_type}, "
            f"Importance: {self.importance}, "
            f"Embedding: {getattr(self, 'embedding', 'N/A')}"
        )


class Conversation(Base):
    """长期对话容器，用于登录用户左侧对话列表与历史恢复。"""

    __tablename__ = "conversations"

    conversation_id = Column(String(128), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(128), nullable=True, index=True, comment="登录用户 ID；访客为空")
    audiences = Column(String(64), nullable=False, index=True)
    title = Column(String(256), nullable=False, default="新对话")
    preview = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    last_session_id = Column(String(128), nullable=True, index=True)
    message_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow, index=True)

    __table_args__ = (
        Index("ix_conversations_user_audience_status_updated", "user_id", "audiences", "status", "updated_at"),
    )


class ConversationSessionLink(Base):
    """conversation_id 与运行时 session_id 的映射。"""

    __tablename__ = "conversation_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(128), nullable=False, index=True)
    session_id = Column(String(128), nullable=False, unique=True, index=True)
    user_id = Column(String(128), nullable=True, index=True)
    audiences = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class ConversationMessage(Base):
    """逐条原始对话消息，供历史恢复与对话列表预览使用。"""

    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(128), nullable=False, index=True)
    session_id = Column(String(128), nullable=False, index=True)
    user_id = Column(String(128), nullable=True, index=True)
    audiences = Column(String(64), nullable=False, index=True)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(64), nullable=True)
    artifact = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    round_id = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow, index=True)

    __table_args__ = (
        Index("ix_conversation_messages_conv_created", "conversation_id", "created_at"),
    )


# 添加数据库操作中的日志
async def init_db(
    db_url: str,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_recycle: int = 3600,
) -> async_sessionmaker[AsyncSession]:
    """
    初始化数据库，并在其中打印日志
    """
    is_pg = "postgresql" in db_url
    engine_kwargs = {"echo": False}
    if is_pg:
        engine_kwargs.update({
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_recycle": pool_recycle,
            "pool_pre_ping": True,
        })
        logger.info(
            f"[{STARTUP}] [init_db] PostgreSQL 连接池设置："
            f"pool_size={pool_size}, max_overflow={max_overflow}, pool_recycle={pool_recycle}s"
        )

    engine = create_async_engine(db_url, **engine_kwargs)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if is_pg:
        # ── pgvector embedding 列 ──
        try:
            async with engine.begin() as conn:
                await conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.execute(sa_text(
                    "ALTER TABLE conversation_memories "
                    "ADD COLUMN IF NOT EXISTS embedding vector(1024)"
                ))
            logger.info(f"[{STARTUP}] | Task=init_db | pgvector 扩展已启用，embedding 列已创建")
        except Exception as e:
            logger.warning(f"[{STARTUP}] | Task=init_db | pgvector 初始化失败: {e}")

        # ── content_hash 列（去重用） ──
        try:
            async with engine.begin() as conn:
                await conn.execute(sa_text(
                    "ALTER TABLE conversation_memories "
                    "ADD COLUMN IF NOT EXISTS content_hash VARCHAR(32)"
                ))
                await conn.execute(sa_text(
                    "CREATE INDEX IF NOT EXISTS ix_conversation_memories_content_hash "
                    "ON conversation_memories (content_hash)"
                ))
            logger.info(f"[{STARTUP}] | Task=init_db | content_hash 列已创建")
        except Exception as e:
            logger.warning(f"[{STARTUP}] | Task=init_db | content_hash 列创建失败: {e}")

        # ── user_id 列（鉴权后的用户唯一标识） ──
        try:
            async with engine.begin() as conn:
                await conn.execute(sa_text(
                    "ALTER TABLE conversation_memories "
                    "ADD COLUMN IF NOT EXISTS user_id VARCHAR(128)"
                ))
                await conn.execute(sa_text(
                    "CREATE INDEX IF NOT EXISTS ix_conversation_memories_user_id "
                    "ON conversation_memories (user_id)"
                ))
            logger.info(f"[{STARTUP}] | Task=init_db | user_id 列已创建")
        except Exception as e:
            logger.warning(f"[{STARTUP}] | Task=init_db | user_id 列创建失败: {e}")

        # ── conversation_id 列（长期对话容器） ──
        try:
            async with engine.begin() as conn:
                await conn.execute(sa_text(
                    "ALTER TABLE conversation_memories "
                    "ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(128)"
                ))
                await conn.execute(sa_text(
                    "CREATE INDEX IF NOT EXISTS ix_conversation_memories_conversation_id "
                    "ON conversation_memories (conversation_id)"
                ))
            logger.info(f"[{STARTUP}] | Task=init_db | conversation_id 列已创建")
        except Exception as e:
            logger.warning(f"[{STARTUP}] | Task=init_db | conversation_id 列创建失败: {e}")

        # ── round_id 列（对话轮次ID） ──
        try:
            async with engine.begin() as conn:
                await conn.execute(sa_text(
                    "ALTER TABLE conversation_memories "
                    "ADD COLUMN IF NOT EXISTS round_id INTEGER"
                ))
            logger.info(f"[{STARTUP}] | Task=init_db | round_id 列已创建")
        except Exception as e:
            logger.warning(f"[{STARTUP}] | Task=init_db | round_id 列创建失败: {e}")

    logger.info(f"[{STARTUP}] | Task=init_db | 数据库初始化完成: {db_url}")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return session_factory


# 假设您有向量生成逻辑，添加日志打印
async def generate_embedding_vector(content: str) -> list[float]:
    """
    生成内容的嵌入向量
    """
    # 示例：替换为实际嵌入生成函数
    vector = []  # 示例，实际情况下应生成真实向量
    try:
        # 这里替换为您实际的生成向量代码 (如通过 OpenAI API 或本地模型)
        vector = [0.01] * 1024  # 示例：生成一个全为 0.01 的向量
        logger.info(f"[{MEM_SYS}] | Task=向量生成 | 向量生成成功: {vector[:5]}... (截断显示)")
    except Exception as e:
        logger.error(f"[{MEM_SYS}] | Task=向量生成 | 向量生成失败: {e}")
    return vector


async def save_conversation_memory(
    session_factory: async_sessionmaker[AsyncSession],
    memory_data: dict
):
    """
    保存对话记忆到数据库
    """
    async with session_factory() as session:
        try:
            # 从数据生成向量
            embedding = await generate_embedding_vector(memory_data["contents"])
            memory_data["embedding"] = embedding

            # 创建 ConversationMemory 实例
            new_memory = ConversationMemory(**memory_data)
            new_memory.log_memory_entry()  # 日志打印条目信息

            # 添加到 session 并提交
            session.add(new_memory)
            await session.commit()
            logger.info(f"[{MEM_SYS}] | Task=记忆保存 | 数据写入成功")
        except Exception as e:
            logger.error(f"[{MEM_SYS}] | Task=记忆保存 | 数据保存失败: {e}")
