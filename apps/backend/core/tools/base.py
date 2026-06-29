"""
工具基类

Tool ABC: 所有面向用户的工具继承此基类。
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from core.conversation.runtime_session import SessionContext


class ToolExecutionError(Exception):
    """工具执行异常。"""

    def __init__(self, tool_name: str, message: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' execution failed: {message}")


class Tool(abc.ABC):
    """工具抽象基类。"""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """工具名称。"""

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """工具描述（供 LLM function calling schema 使用）。"""

    @property
    def definition(self) -> Dict[str, Any]:
        """
        返回工具定义（供 LLM function calling 使用）。

        Returns:
            Dict: 包含 name, description 的工具定义
        """
        return {
            "name": self.name,
            "description": self.description,
        }

    @abc.abstractmethod
    async def execute(self, ctx: SessionContext, **kwargs: Any) -> Any:
        """
        执行工具。

        Args:
            ctx:    SessionContext 实例
            kwargs: 工具参数

        Returns:
            工具执行结果
        """
