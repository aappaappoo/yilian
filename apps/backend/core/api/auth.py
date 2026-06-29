"""
认证 API 路由

POST /api/auth/register       — 注册
POST /api/auth/login          — 登录（账号密码 / API Key）
POST /api/auth/api-keys/reset — 重置 API Key（需登录态）
POST /api/auth/api-keys/revoke — 吊销 API Key（需登录态）
GET  /api/auth/api-keys       — 查看 API Key 列表（需登录态）
GET  /api/auth/me             — 获取当前用户信息（需登录态）
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.auth.dependencies import CurrentUser, get_current_user
from core.auth.models import ApiKey, User
from core.auth.schemas import (
    ApiKeyItem,
    ApiKeyListResponse,
    ApiKeyResetResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    RevokeRequest,
    RevokeResponse,
)
from core.auth.service import (
    list_api_keys,
    login_with_api_key,
    login_with_password,
    register_user,
    reset_api_key,
    revoke_api_key,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 全局 session_factory，由 main.py 的 lifespan 注入
_session_factory: Optional[async_sessionmaker] = None


def set_session_factory(factory: async_sessionmaker) -> None:
    """由 main.py 在 lifespan 中调用，注入数据库 session 工厂"""
    global _session_factory
    _session_factory = factory


def _get_session_factory() -> async_sessionmaker:
    if _session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库尚未就绪",
        )
    return _session_factory


def _get_client_info(request: Request):
    """从请求中获取 IP 和 User-Agent"""
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")[:512]
    return ip, ua


# ── 注册 ──────────────────────────────────────────────────────────────────────


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    """注册新用户，返回用户信息和仅此一次展示的 API Key 明文"""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            user, raw_key = await register_user(
                session=session,
                username=body.username,
                password=body.password,
                display_name=body.display_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return RegisterResponse(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        api_key=raw_key,
        key_prefix=raw_key[:8],
    )


# ── 登录 ──────────────────────────────────────────────────────────────────────


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    """
    登录端点，支持两种方式：
    - method=password：使用账号密码登录
    - method=api_key ：使用 API Key 登录
    """
    factory = _get_session_factory()
    ip, ua = _get_client_info(request)

    async with factory() as session:
        try:
            if body.method == "password":
                if not body.username or not body.password:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="账号密码登录需要提供 username 和 password",
                    )
                user, token = await login_with_password(
                    session=session,
                    username=body.username,
                    password=body.password,
                    ip_address=ip,
                    user_agent=ua,
                )
            elif body.method == "api_key":
                if not body.api_key:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="API Key 登录需要提供 api_key",
                    )
                user, token = await login_with_api_key(
                    session=session,
                    raw_key=body.api_key,
                    ip_address=ip,
                    user_agent=ua,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="不支持的登录方式，请使用 'password' 或 'api_key'",
                )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    from core.config import settings as cfg
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=cfg.jwt_expire_hours * 3600,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


# ── API Key 管理 ───────────────────────────────────────────────────────────────


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def get_api_keys(current_user: CurrentUser = Depends(get_current_user)):
    """查看当前用户的 API Key 列表（仅返回 prefix + name + status，不返回完整 key）"""
    factory = _get_session_factory()
    async with factory() as session:
        keys = await list_api_keys(session=session, user_id=current_user.user_id)

    items = [
        ApiKeyItem(
            id=k.id,
            key_prefix=k.key_prefix,
            name=k.name,
            status=k.status,
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
            created_at=k.created_at,
            revoked_at=k.revoked_at,
        )
        for k in keys
    ]
    return ApiKeyListResponse(items=items)


@router.post("/api-keys/reset", response_model=ApiKeyResetResponse)
async def reset_key(current_user: CurrentUser = Depends(get_current_user)):
    """重置 API Key：吊销所有旧 key，生成并返回新 key 明文（仅一次）"""
    factory = _get_session_factory()
    async with factory() as session:
        new_key, raw_key = await reset_api_key(session=session, user_id=current_user.user_id)

    return ApiKeyResetResponse(
        api_key=raw_key,
        key_prefix=new_key.key_prefix,
    )


@router.post("/api-keys/revoke", response_model=RevokeResponse)
async def revoke_key(body: RevokeRequest, current_user: CurrentUser = Depends(get_current_user)):
    """吊销指定 API Key"""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            await revoke_api_key(
                session=session,
                user_id=current_user.user_id,
                key_id=str(body.key_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return RevokeResponse()


# ── 当前用户信息 ───────────────────────────────────────────────────────────────


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)):
    """获取当前登录用户的详细信息"""
    from sqlalchemy import select

    factory = _get_session_factory()
    async with factory() as session:
        user = (await session.execute(
            select(User).where(User.id == current_user.user_id)
        )).scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    return MeResponse(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
    )
