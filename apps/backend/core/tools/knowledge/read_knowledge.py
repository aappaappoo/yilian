"""
ReadDomainDocTool

读取当前角色领域知识库中的指定 Markdown 文件全文，
用于回答需要引用原文的政策/标准/流程问题。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from core.tools.base import Tool, ToolExecutionError
from core.tools.knowledge.paths import safe_resolve

if TYPE_CHECKING:
    from core.conversation.runtime_session import SessionContext

# 文件大小硬限制：200 KB
_MAX_BYTES = 200 * 1024


class ReadDomainDocTool(Tool):
    """读取当前角色领域知识库中的指定 Markdown 文件全文。"""

    @property
    def name(self) -> str:
        return "read_domain_doc"

    @property
    def description(self) -> str:
        return (
            "读取当前角色领域知识库中的指定 Markdown 文件全文，"
            "用于回答需要引用原文的政策/标准/流程问题。"
            "file 参数必须是 list_domain_knowledge 返回清单中的文件名。"
        )

    @property
    def definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": (
                            "文件名（如 失能老年人养老服务消费补贴.md），"
                            "必须是 list_domain_knowledge 返回清单中的文件名"
                        ),
                    }
                },
                "required": ["file"],
            },
        }

    async def execute(self, ctx: "SessionContext", file: str = "", **kwargs: Any) -> Dict[str, Any]:
        """
        读取指定 Markdown 文件全文。

        Args:
            ctx:  SessionContext 实例（提供 audience）
            file: 文件名（相对于 domain/ 目录）

        Returns:
            {"audience": "...", "file": "...", "content": "...", "bytes": <原始大小>, "truncated": bool}

        Raises:
            ToolExecutionError: 路径越界、非 .md 后缀、文件不存在
        """
        if not file:
            raise ToolExecutionError(self.name, "参数 'file' 不能为空")

        # 仅允许 .md 后缀
        if not file.lower().endswith(".md"):
            raise ToolExecutionError(
                self.name,
                f"仅支持读取 .md 文件，'{file}' 后缀不合法",
            )

        audience: str = ctx.audience

        # 路径边界校验（防止路径穿越）
        resolved = safe_resolve(audience, file)

        # 文件存在性检查
        if not resolved.is_file():
            raise ToolExecutionError(
                self.name,
                f"文件 '{file}' 不存在，请先调用 list_domain_knowledge 查看可用清单",
            )

        raw_size = resolved.stat().st_size
        truncated = raw_size > _MAX_BYTES

        with resolved.open(encoding="utf-8", errors="replace") as f:
            if truncated:
                content = f.read(_MAX_BYTES)
            else:
                content = f.read()

        return {
            "audience": audience,
            "file": file,
            "content": content,
            "bytes": raw_size,
            "truncated": truncated,
        }
