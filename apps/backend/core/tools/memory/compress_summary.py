"""
对话记录摘要化工具

将当前对话窗口的消息压缩为摘要，写入 PostgreSQL 数据库。
可由系统自动调用（定时窗口过期），也可由用户指令触发。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from core.logging_utils import MEM_SYS
from core.tools.base import Tool, ToolExecutionError

if TYPE_CHECKING:
    from core.conversation.runtime_session import SessionContext


class CompressSummaryTool(Tool):
    """
    对话记录摘要化工具。

    支持两种调用模式：
    1. 用户指令：用户要求总结对话（如 "帮我总结一下我们聊了什么"）
    2. 系统自动：定时器触发或对话消息数超过阈值时自动压缩

    执行后：
    - 将当前对话消息生成摘要，写入 PostgreSQL
    - 提取其中的重要事件，写入 PostgreSQL
    """

    @property
    def name(self) -> str:
        return "compress_conversation"

    @property
    def description(self) -> str:
        return (
            "将当前对话压缩为摘要并保存。当需要总结对话内容时调用此工具。"
            "系统也会在对话窗口过期时自动调用。"
        )

    @property
    def definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "压缩原因（可选），如：用户请求、窗口过期、会话结束",
                    },
                },
                "required": [],
            },
        }

    async def execute(self, ctx: SessionContext, **kwargs: Any) -> str:
        reason = kwargs.get("reason", "用户请求")

        try:
            result = await ctx.compress_conversation()
            if result:
                logger.info(
                    f"[{MEM_SYS}] | Task=压缩摘要生成 | [CompressSummaryTool] 完成: "
                    f"ns={ctx.namespace}, reason={reason}"
                )
                return "对话已压缩为摘要并保存。"
            else:
                return "当前没有需要压缩的对话记录，或压缩功能暂不可用。"
        except Exception as e:
            logger.error(f"[{MEM_SYS}] | Task=压缩摘要生成 | [CompressSummaryTool] 失败: {e}")
            raise ToolExecutionError(self.name, str(e))
