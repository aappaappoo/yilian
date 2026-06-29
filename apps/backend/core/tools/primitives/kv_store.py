"""
KV 存储原语

set/get/list/delete，无文案。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class KVStore:
    """KV 存储原语：set/get/list/delete，不含业务文案。"""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}

    async def set(self, key: str, value: Any) -> None:
        """写入 KV。"""
        self._data[key] = value

    async def get(self, key: str) -> Optional[Any]:
        """读取 KV，不存在返回 None。"""
        return self._data.get(key)

    async def list_keys(self, prefix: str = "") -> List[str]:
        """列出匹配前缀的所有 key。"""
        return [k for k in self._data if k.startswith(prefix)]

    async def delete(self, key: str) -> bool:
        """删除 KV，不存在返回 False。"""
        if key in self._data:
            del self._data[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        """检查 key 是否存在。"""
        return key in self._data


class InMemoryKVStore(KVStore):
    """基于内存的 KV 存储实现（与 KVStore 相同，用于语义明确的场景）。"""
    pass


class SQLiteKVStore(KVStore):
    """SQLite-backed KV store for production task/session state."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._initialized = False

    async def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False, default=str)
        async with self._lock:
            await self._ensure_initialized()
            await asyncio.to_thread(self._set_sync, str(key), payload)

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            await self._ensure_initialized()
            row = await asyncio.to_thread(self._get_sync, str(key))
        if row is None:
            return None
        try:
            return json.loads(row)
        except json.JSONDecodeError:
            return row

    async def list_keys(self, prefix: str = "") -> List[str]:
        async with self._lock:
            await self._ensure_initialized()
            return await asyncio.to_thread(self._list_keys_sync, str(prefix or ""))

    async def delete(self, key: str) -> bool:
        async with self._lock:
            await self._ensure_initialized()
            return await asyncio.to_thread(self._delete_sync, str(key))

    async def exists(self, key: str) -> bool:
        async with self._lock:
            await self._ensure_initialized()
            return await asyncio.to_thread(self._exists_sync, str(key))

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        await asyncio.to_thread(self._init_sync)
        self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._path), timeout=30.0)

    def _init_sync(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def _set_sync(self, key: str, payload: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kv_store(key, value, updated_at)
                VALUES(?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, payload),
            )
            conn.commit()

    def _get_sync(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else None

    def _list_keys_sync(self, prefix: str) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key FROM kv_store WHERE key LIKE ? ORDER BY key",
                (f"{prefix}%",),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def _delete_sync(self, key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0

    def _exists_sync(self, key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM kv_store WHERE key = ? LIMIT 1", (key,)).fetchone()
        return row is not None
