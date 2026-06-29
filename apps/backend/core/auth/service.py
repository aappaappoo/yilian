"""
认证业务逻辑

- 用户注册
- 账号密码登录 / API Key 登录
- API Key 管理（查询 / 重置 / 吊销）
- 登录审计写入
- 管理员初始化
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import jwt
from loguru import logger
from core.logging_utils import STARTUP
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.auth.models import ApiKey, AuthCredential, LoginAudit, User
from core.auth.utils import (
    generate_api_key,
    get_key_prefix,
    hash_api_key,
    hash_password,
    verify_password,
)
from core.config import settings


# ── JWT ────────────────────────────────────────────────────────────────────────


def create_access_token(user_id: str, username: str, role: str) -> str:
    """签发 JWT，有效期由配置项 jwt_expire_hours 控制"""
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


# ── 注册 ───────────────────────────────────────────────────────────────────────


async def register_user(
    session: AsyncSession,
    username: str,
    password: str,
    display_name: Optional[str] = None,
    role: str = "user",
) -> Tuple[User, str]:
    """
    注册新用户。

    Returns:
        (User, raw_api_key) — 原始 API Key 仅此一次返回
    """
    # 检查用户名是否已存在
    existing = (await session.execute(
        select(User).where(User.username == username)
    )).scalar_one_or_none()
    if existing:
        raise ValueError(f"用户名 '{username}' 已被占用")

    # 创建用户
    user = User(
        id=uuid.uuid4(),
        username=username,
        display_name=display_name,
        role=role,
        status="active",
    )
    session.add(user)
    await session.flush()  # 先把 user 写入数据库，确保外键可用

    # 写入密码凭证
    credential = AuthCredential(
        id=uuid.uuid4(),
        user_id=user.id,
        auth_type="password",
        credential_hash=hash_password(password),
        status="active",
    )
    session.add(credential)

    # 生成 API Key
    raw_key = generate_api_key()
    api_key = ApiKey(
        id=uuid.uuid4(),
        user_id=user.id,
        api_key_hash=hash_api_key(raw_key),
        key_prefix=get_key_prefix(raw_key),
        name="默认 Key",
        status="active",
    )
    session.add(api_key)

    await session.commit()
    await session.refresh(user)
    logger.info(f"[{STARTUP}] | Task=用户注册 | 新用户注册成功: {username} (id={user.id})")
    return user, raw_key


# ── 登录 ───────────────────────────────────────────────────────────────────────


async def login_with_password(
    session: AsyncSession,
    username: str,
    password: str,
    ip_address: str,
    user_agent: str,
) -> Tuple[User, str]:
    """
    账号密码登录。

    Returns:
        (User, access_token)

    Raises:
        ValueError: 认证失败
    """
    user = (await session.execute(
        select(User).where(User.username == username)
    )).scalar_one_or_none()

    if user is None:
        await _write_audit(session, None, "password", ip_address, user_agent,
                           "failed", "user_not_found")
        raise ValueError("用户名或密码错误")

    if user.status != "active":
        await _write_audit(session, user.id, "password", ip_address, user_agent,
                           "failed", "user_disabled")
        raise ValueError("账户已被禁用")

    # 查找密码凭证
    credential = (await session.execute(
        select(AuthCredential).where(
            AuthCredential.user_id == user.id,
            AuthCredential.auth_type == "password",
            AuthCredential.status == "active",
        )
    )).scalar_one_or_none()

    if credential is None or not verify_password(password, credential.credential_hash):
        await _write_audit(session, user.id, "password", ip_address, user_agent,
                           "failed", "invalid_password")
        raise ValueError("用户名或密码错误")

    token = create_access_token(str(user.id), user.username, user.role)
    await _write_audit(session, user.id, "password", ip_address, user_agent, "success", None)
    logger.info(f"[{STARTUP}] | Task=用户登录 | 账号密码登录成功: {username} (ip={ip_address})")
    return user, token


async def login_with_api_key(
    session: AsyncSession,
    raw_key: str,
    ip_address: str,
    user_agent: str,
) -> Tuple[User, str]:
    """
    API Key 登录。

    Returns:
        (User, access_token)

    Raises:
        ValueError: 认证失败
    """
    key_hash = hash_api_key(raw_key)
    api_key_obj = (await session.execute(
        select(ApiKey).where(ApiKey.api_key_hash == key_hash)
    )).scalar_one_or_none()

    if api_key_obj is None:
        await _write_audit(session, None, "api_key", ip_address, user_agent,
                           "failed", "key_not_found")
        raise ValueError("API Key 无效")

    if api_key_obj.status != "active":
        await _write_audit(session, api_key_obj.user_id, "api_key", ip_address, user_agent,
                           "failed", "key_revoked")
        raise ValueError("API Key 已吊销")

    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now():
        await _write_audit(session, api_key_obj.user_id, "api_key", ip_address, user_agent,
                           "failed", "key_expired")
        raise ValueError("API Key 已过期")

    # 查询关联用户
    user = (await session.execute(
        select(User).where(User.id == api_key_obj.user_id)
    )).scalar_one_or_none()

    if user is None or user.status != "active":
        await _write_audit(session, api_key_obj.user_id, "api_key", ip_address, user_agent,
                           "failed", "user_disabled")
        raise ValueError("账户已被禁用")

    # 更新最后使用时间
    api_key_obj.last_used_at = datetime.now().replace(microsecond=0)
    await session.commit()

    token = create_access_token(str(user.id), user.username, user.role)
    await _write_audit(session, user.id, "api_key", ip_address, user_agent, "success", None)
    logger.info(f"[{STARTUP}] | Task=API Key登录 | API Key 登录成功: {user.username} (ip={ip_address})")
    return user, token


# ── API Key 管理 ────────────────────────────────────────────────────────────────


async def list_api_keys(session: AsyncSession, user_id: str) -> List[ApiKey]:
    """查询用户的所有 API Key"""
    result = await session.execute(
        select(ApiKey).where(ApiKey.user_id == uuid.UUID(user_id))
    )
    return list(result.scalars().all())


async def reset_api_key(session: AsyncSession, user_id: str) -> Tuple[ApiKey, str]:
    """
    重置 API Key：吊销所有旧 active key，生成并返回新 key 明文（仅一次）。

    Returns:
        (ApiKey, raw_api_key)
    """
    uid = uuid.UUID(user_id)

    # 吊销所有 active key
    now = datetime.now().replace(microsecond=0)
    await session.execute(
        update(ApiKey)
        .where(ApiKey.user_id == uid, ApiKey.status == "active")
        .values(status="revoked", revoked_at=now)
    )

    # 生成新 key
    raw_key = generate_api_key()
    new_key = ApiKey(
        id=uuid.uuid4(),
        user_id=uid,
        api_key_hash=hash_api_key(raw_key),
        key_prefix=get_key_prefix(raw_key),
        name="默认 Key",
        status="active",
    )
    session.add(new_key)
    await session.commit()
    await session.refresh(new_key)
    logger.info(f"[{STARTUP}] | Task=API Key管理 | API Key 已重置: user_id={user_id}")
    return new_key, raw_key


async def revoke_api_key(session: AsyncSession, user_id: str, key_id: str) -> None:
    """吊销指定 API Key（必须属于当前用户）"""
    uid = uuid.UUID(user_id)
    kid = uuid.UUID(key_id)
    api_key_obj = (await session.execute(
        select(ApiKey).where(ApiKey.id == kid, ApiKey.user_id == uid)
    )).scalar_one_or_none()

    if api_key_obj is None:
        raise ValueError("API Key 不存在或无权操作")

    now = datetime.now().replace(microsecond=0)
    api_key_obj.status = "revoked"
    api_key_obj.revoked_at = now
    await session.commit()
    logger.info(f"[{STARTUP}] | Task=API Key管理 | API Key 已吊销: id={key_id} user_id={user_id}")


# ── 审计写入 ───────────────────────────────────────────────────────────────────


async def _write_audit(
    session: AsyncSession,
    user_id: Optional[uuid.UUID],
    login_method: str,
    ip_address: str,
    user_agent: str,
    status: str,
    failure_reason: Optional[str],
) -> None:
    """写入登录审计记录（只追加，不修改不删除）"""
    audit = LoginAudit(
        id=uuid.uuid4(),
        user_id=user_id,
        login_method=login_method,
        ip_address=ip_address,
        user_agent=user_agent,
        status=status,
        failure_reason=failure_reason,
    )
    session.add(audit)
    await session.commit()


# ── 管理员初始化 ────────────────────────────────────────────────────────────────


async def init_admin(session_factory: async_sessionmaker) -> None:
    """
    系统启动时初始化管理员账号。

    如果 users 表中不存在 username=settings.admin_username 且 role='admin' 的记录，
    则自动创建管理员用户、密码凭证和 API Key，并将原始 API Key 输出到日志。
    """
    async with session_factory() as session:
        existing = (await session.execute(
            select(User).where(
                User.username == settings.admin_username,
                User.role == "admin",
            )
        )).scalar_one_or_none()

        if existing:
            logger.info(f"[{STARTUP}] | Task=管理员初始化 | 管理员账号已存在，跳过初始化: {settings.admin_username}")
            return

        logger.info(f"[{STARTUP}] | Task=管理员初始化 | 未检测到管理员账号，开始初始化: {settings.admin_username}")
        user, raw_key = await register_user(
            session=session,
            username=settings.admin_username,
            password=settings.admin_password,
            display_name="管理员",
            role="admin",
        )
        # 将原始 API Key 输出到日志（仅首次初始化）
        logger.warning(
            f"[{STARTUP}] | Task=管理员初始化 | ⚠️  管理员 API Key（仅展示一次，请妥善保存）: {raw_key}"
        )
