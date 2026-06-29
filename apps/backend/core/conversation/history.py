"""
历史管理器

窗口裁剪，保留 system prompt。
"""

from __future__ import annotations

from typing import Dict, List

from core.conversation.store import ConversationStore


class HistoryManager:
    """
    对话历史管理器。
    负责窗口裁剪（保留 system prompt）。
    """

    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    async def get_recent(self, key: str, n: int) -> List[Dict[str, str]]:
        """
        获取最近 n 条消息，保留 system prompt。
        """
        messages = await self._store.get_messages(key)
        if not messages:
            return []

        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        recent = non_system[-n:] if len(non_system) > n else non_system

        return system_msgs + recent