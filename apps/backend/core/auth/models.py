"""
认证模块 ORM 模型

包含 4 张表：
  - users          用户主体
  - auth_credentials 账号密码凭证
  - api_keys       API Key 凭证
  - login_audit    登录审计日志
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

# 与 conversation 模块共用同一个 Base，确保 init_db() 能统一建表
from core.conversation.models import Base


def _utcnow() -> datetime:
    """返回不带微秒的当前时间"""
    return datetime.now().replace(microsecond=0)


class User(Base):
    """用户主体表，只存身份信息，不存任何凭证"""
    __tablename__ = "users"

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    username = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(128), nullable=True)
    role = Column(String(32), nullable=False, default="user")          # admin / user
    status = Column(String(32), nullable=False, default="active")      # active / disabled
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    credentials = relationship("AuthCredential", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"


class AuthCredential(Base):
    """账号密码凭证表"""
    __tablename__ = "auth_credentials"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    auth_type = Column(String(32), nullable=False, default="password")  # password / oauth / ldap
    credential_hash = Column(String(256), nullable=False)               # bcrypt hash
    status = Column(String(32), nullable=False, default="active")       # active / revoked
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    user = relationship("User", back_populates="credentials")

    __table_args__ = (
        Index("ix_auth_credentials_user_type", "user_id", "auth_type"),
    )

    def __repr__(self) -> str:
        return f"<AuthCredential id={self.id} user_id={self.user_id} type={self.auth_type}>"


class ApiKey(Base):
    """API Key 凭证表，数据库只存哈希值，原始 key 仅在生成时返回一次"""
    __tablename__ = "api_keys"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_key_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 哈希
    key_prefix = Column(String(8), nullable=False)                   # 原始 key 前 8 位明文
    name = Column(String(128), nullable=True)                        # 用户自定义 key 名称
    status = Column(String(32), nullable=False, default="active")    # active / revoked
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    revoked_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id} user_id={self.user_id} prefix={self.key_prefix}>"


class LoginAudit(Base):
    """登录审计日志表（只追加，不修改不删除）"""
    __tablename__ = "login_audit"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    login_method = Column(String(32), nullable=False)    # password / api_key
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(String(512), nullable=False)
    status = Column(String(32), nullable=False)          # success / failed
    failure_reason = Column(String(128), nullable=True)  # invalid_password / key_revoked / user_disabled
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<LoginAudit id={self.id} method={self.login_method} status={self.status}>"
