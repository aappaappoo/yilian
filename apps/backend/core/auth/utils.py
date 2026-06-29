"""
认证工具函数

- bcrypt 密码哈希/验证（cost factor=12）
- API Key 生成（sk- 前缀 + 32 字节随机 hex）
- SHA-256 哈希（用于存储 API Key）
"""

from __future__ import annotations

import hashlib
import secrets

import bcrypt


# ── 密码相关 ────────────────────────────────────────────────────────────────


def hash_password(plain_password: str) -> str:
    """使用 bcrypt 对密码进行哈希，cost factor=12"""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与 bcrypt 哈希是否匹配"""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


# ── API Key 相关 ──────────────────────────────────────────────────────────────


def generate_api_key() -> str:
    """
    生成原始 API Key。
    格式：sk- + 32 字节随机 hex（共 67 字符）
    原始 key 仅在生成时返回一次，后端不保留。
    """
    return "sk-" + secrets.token_hex(32)


def hash_api_key(api_key: str) -> str:
    """对 API Key 进行 SHA-256 哈希，用于数据库存储"""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def get_key_prefix(api_key: str) -> str:
    """取 API Key 前 8 位明文，用于用户辨识（如 'sk-a3f2'）"""
    return api_key[:8]
