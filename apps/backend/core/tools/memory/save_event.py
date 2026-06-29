"""
保存重要事件工具

用户说"帮我记一下XXX"时触发。
获取当前完整对话历史 → 调用 LLM 分析 → 写入 SQL。
所有字段（msg_type / content_type / importance / contents）由 LLM 自行判断。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from core.logging_utils import MEM_SYS
from core.tools.base import Tool, ToolExecutionError

if TYPE_CHECKING:
    from core.conversation.runtime_session import SessionContext


class SaveEventTool(Tool):
    """
    被动记忆工具。

    当用户明确要求记住某事时（如"帮我记住明天要去医院"），
    获取当前全部对话历史，调用 LLM 统一分析后写入 SQL。
    """

    @property
    def name(self) -> str:
        return "save_important_event"

    @property
    def description(self) -> str:
        return (
            "保存重要事件到长期记忆。当用户明确要求记住某事时调用此工具。"
            "会获取当前完整对话，由大模型统一分析后保存。"
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
                        "description": "用户原始请求，如：帮我记住明天要去医院",
                    },
                },
                "required": [],
            },
        }

    async def execute(self, ctx: SessionContext, **kwargs: Any) -> str:
        reason = kwargs.get("reason", "用户请求保存")

        try:
            # 复用 analyze_and_save — 获取全部对话 → LLM 分析 → 写入 SQL
            if ctx._context_manager is None:
                return "记忆保存功能暂不可用。"

            result = await ctx._context_manager.analyze_and_save(
                namespace=ctx.namespace,
                session_id=ctx._session_id,
                speaker_id=ctx._speaker_id,
                audience=ctx._audience,
                context_config=ctx._context_config,
                user_id=ctx.user_id,
                conversation_id=ctx.conversation_id,
            )
            logger.info(f"[{MEM_SYS}] | Task=知识更新 | [SaveEventTool] 完成: reason={reason}, result={result}")
            return result
        except Exception as e:
            logger.error(f"[{MEM_SYS}] | Task=知识更新 | [SaveEventTool] 失败: {e}")
            raise ToolExecutionError(self.name, str(e))
