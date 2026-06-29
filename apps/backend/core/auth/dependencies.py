"""
认证 FastAPI 依赖项

- get_current_user: 验证 Bearer JWT Token，返回当前用户信息
"""

from __future__ import annotations

from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings


# Bearer Token 提取器
_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    """从 JWT 解析出的当前用户信息"""

    def __init__(self, user_id: str, username: str, role: str):
        self.user_id = user_id
        self.username = username
        self.role = role


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    """
    FastAPI 依赖项：验证 Bearer JWT Token。

    - 未携带 Token → 401
    - Token 无效/过期 → 401
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证 Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=["HS256"],
        )
        user_id: Optional[str] = payload.get("sub")
        username: Optional[str] = payload.get("username")
        role: Optional[str] = payload.get("role")
        if not user_id or not username or not role:
            raise ValueError("Token payload 不完整")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(user_id=user_id, username=username, role=role)
