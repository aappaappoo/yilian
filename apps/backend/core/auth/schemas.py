"""
认证模块 Pydantic Schemas

定义所有请求体和响应体的数据结构。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── 注册 ──────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """注册请求体"""
    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    password: str = Field(..., min_length=6, description="密码（至少 6 位）")
    display_name: Optional[str] = Field(None, max_length=128, description="显示名称（可选）")


class RegisterResponse(BaseModel):
    """注册响应体（含仅此一次展示的 API Key 明文）"""
    user_id: UUID
    username: str
    display_name: Optional[str]
    role: str
    api_key: str = Field(..., description="原始 API Key，仅此一次返回，请妥善保存")
    key_prefix: str = Field(..., description="API Key 前 8 位，用于辨识")


# ── 登录 ──────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    """登录请求体（支持 password / api_key 两种方式）"""
    method: str = Field(..., description="登录方式：password 或 api_key")
    username: Optional[str] = Field(None, description="账号密码登录时必填")
    password: Optional[str] = Field(None, description="账号密码登录时必填")
    api_key: Optional[str] = Field(None, description="API Key 登录时必填")


class LoginResponse(BaseModel):
    """登录响应体"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token 有效期（秒）")
    user_id: UUID
    username: str
    role: str


# ── API Key 管理 ───────────────────────────────────────────────────────────────


class ApiKeyItem(BaseModel):
    """API Key 列表项（不暴露完整 key）"""
    id: UUID
    key_prefix: str
    name: Optional[str]
    status: str
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    revoked_at: Optional[datetime]


class ApiKeyListResponse(BaseModel):
    """API Key 列表响应"""
    items: List[ApiKeyItem]


class ApiKeyResetResponse(BaseModel):
    """重置 API Key 响应（仅此一次返回新 key 明文）"""
    api_key: str = Field(..., description="新的原始 API Key，仅此一次返回，请妥善保存")
    key_prefix: str


class RevokeRequest(BaseModel):
    """吊销 API Key 请求"""
    key_id: UUID = Field(..., description="要吊销的 API Key ID")


class RevokeResponse(BaseModel):
    """吊销 API Key 响应"""
    message: str = "API Key 已吊销"


# ── 用户信息 ──────────────────────────────────────────────────────────────────


class MeResponse(BaseModel):
    """当前用户信息响应"""
    user_id: UUID
    username: str
    display_name: Optional[str]
    role: str
    status: str
    created_at: datetime
