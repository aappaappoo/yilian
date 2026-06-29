"""
核心记忆工具模块

提供对话记录摘要化和重要事件保存的 tool call 能力。
可由系统自动调用，也可由用户指令触发。
"""

from core.tools.memory.save_event import SaveEventTool
from core.tools.memory.compress_summary import CompressSummaryTool

__all__ = ["SaveEventTool", "CompressSummaryTool"]
