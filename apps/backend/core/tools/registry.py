"""
工具注册表

ToolRegistry: 注册、查找、列出工具 schema。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from core.tools.base import Tool
from loguru import logger

from core.logging_utils import STARTUP, TOOL_CALL


class ToolNotFoundError(Exception):
    """工具未注册异常。"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Tool '{name}' is not registered.")


class ToolDuplicateError(Exception):
    """工具重复注册异常。"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Tool '{name}' is already registered.")


class ToolRegistry:
    """工具注册表。"""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具。"""
        if tool.name in self._tools:
            raise ToolDuplicateError(tool.name)
        self._tools[tool.name] = tool
        logger.info(f"[{STARTUP}] | Task=工具注册 | register: tool='{tool.name}', 当前工具数={len(self._tools)}")

    def unregister(self, name: str) -> bool:
        """注销一个工具，返回是否成功。"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Tool:
        """
        获取已注册的工具。

        Raises:
            ToolNotFoundError: 工具未注册
        """
        if name not in self._tools:
            logger.warning(f"[{TOOL_CALL}] | Task=工具调用 | get: tool='{name}' 未注册")
            raise ToolNotFoundError(name)
        return self._tools[name]

    def has(self, name: str) -> bool:
        """检查工具是否已注册。"""
        return name in self._tools

    def list_names(self) -> List[str]:
        """列出所有已注册工具的名称。"""
        return list(self._tools.keys())

    def list_definitions(self) -> List[Dict]:
        """列出所有已注册工具的 schema 定义。"""
        return [t.definition for t in self._tools.values()]

    def get_schemas(self, exclude: Optional[Set[str]] = None) -> List[Dict]:
        """列出所有已注册工具的 schema 定义，可排除指定工具。"""
        exclude = exclude or set()
        schemas = [t.definition for t in self._tools.values() if t.name not in exclude]
        return schemas

    def get_all(self) -> Dict[str, Tool]:
        """返回所有已注册工具的副本。"""
        return dict(self._tools)

    @property
    def count(self) -> int:
        """已注册工具数量。"""
        return len(self._tools)
