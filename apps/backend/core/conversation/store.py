"""
对话存储抽象 + InMemory 实现

ConversationStore ABC 定义存储接口，InMemoryStore 为内存实现（开发/测试用）。
生产环境使用 SQLStore (PostgreSQL) 代替。
"""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional


class ConversationStore(abc.ABC):
    """对话存储抽象基类。"""

    @abc.abstractmethod
    async def append_message(self, key: str, role: str, content: str) -> None:
        """追加一条对话消息。"""

    @abc.abstractmethod
    async def get_messages(self, key: str, start: int = 0, end: int = -1) -> List[Dict[str, str]]:
        """获取指定 key 的所有消息。"""

    @abc.abstractmethod
    async def get_message_count(self, key: str) -> int:
        """获取指定 key 的消息数量。"""

    @abc.abstractmethod
    async def replace_messages(self, key: str, messages: List[Dict[str, str]]) -> None:
        """替换指定 key 的所有消息。"""

    @abc.abstractmethod
    async def clear(self, key: str) -> None:
        """清空指定 key 的所有消息。"""

    @abc.abstractmethod
    async def save_summary(self, key: str, summary: str) -> None:
        """保存对话摘要。"""

    @abc.abstractmethod
    async def get_summary(self, key: str) -> Optional[str]:
        """获取对话摘要。"""


class InMemoryStore(ConversationStore):
    """
    基于内存的对话存储实现。
    仅用于开发/测试，生产环境应使用 SQLStore (PostgreSQL)。
    """

    def __init__(self) -> None:
        self._messages: Dict[str, List[Dict[str, str]]] = {}
        self._summaries: Dict[str, str] = {}

    async def append_message(self, key: str, role: str, content: str) -> None:
        if key not in self._messages:
            self._messages[key] = []
        self._messages[key].append({"role": role, "content": content})

    async def get_messages(self, key: str, start: int = 0, end: int = -1) -> List[Dict[str, str]]:
        msgs = self._messages.get(key, [])
        if start == 0 and end == -1:
            return list(msgs)
        if end >= 0:
            result = list(msgs[start:end + 1])
            return result
        result = list(msgs[start:])
        return result

    async def get_message_count(self, key: str) -> int:
        count = len(self._messages.get(key, []))
        return count

    async def replace_messages(self, key: str, messages: List[Dict[str, str]]) -> None:
        self._messages[key] = list(messages)

    async def clear(self, key: str) -> None:
        self._messages.pop(key, None)
        self._summaries.pop(key, None)

    async def save_summary(self, key: str, summary: str) -> None:
        self._summaries[key] = summary

    async def get_summary(self, key: str) -> Optional[str]:
        summary = self._summaries.get(key)
        return summary
