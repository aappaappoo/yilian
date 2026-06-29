"""
ListDomainKnowledgeTool

列出当前 audience 可用的领域知识文件清单（含标题/摘要），
用于回答政策/流程/标准类问题前的预检索。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

import yaml

from core.tools.base import Tool
from core.tools.knowledge.paths import get_domain_root

if TYPE_CHECKING:
    from core.conversation.runtime_session import SessionContext


class ListDomainKnowledgeTool(Tool):
    """列出当前角色可用的领域知识文件清单（含标题/主题/摘要）。"""

    @property
    def name(self) -> str:
        return "list_domain_knowledge"

    @property
    def description(self) -> str:
        return (
            "列出当前角色可用的领域知识文件清单（含标题/主题/摘要），"
            "用于回答政策/流程/标准类问题前的预检索。"
            "调用此工具可了解有哪些可用文件，再通过 read_domain_doc 读取具体内容。"
        )

    @property
    def definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }

    async def execute(self, ctx: "SessionContext", **kwargs: Any) -> Dict[str, Any]:
        """
        列出当前 audience 的领域知识文件清单。

        优先读取 _index.yaml；若无则自动扫描 *.md 文件并解析标题。

        Returns:
            {"audience": "...", "docs": [...]}
        """
        audience: str = ctx.audience
        domain_root = get_domain_root(audience)

        if domain_root is None:
            return {
                "audience": audience,
                "docs": [],
                "note": "当前角色没有配置领域知识库",
            }

        # 读取 _index.yaml
        index_path = domain_root / "_index.yaml"
        if index_path.is_file():
            with index_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            docs: List[Any] = data.get("docs", []) if isinstance(data, dict) else []
            return {"audience": audience, "docs": docs}

        # _index.yaml 不存在时扫描 *.md 文件
        docs = []
        for md_file in sorted(domain_root.glob("*.md")):
            title = _parse_title(md_file)
            docs.append(
                {
                    "file": md_file.name,
                    "title": title,
                    "size_bytes": md_file.stat().st_size,
                }
            )

        return {"audience": audience, "docs": docs}


def _parse_title(path: Any) -> str:
    """从 Markdown 文件第一行解析 # 标题，去掉前导 # 和空白。"""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#"):
                    return line.lstrip("#").strip()
        return path.name
    except OSError:
        return path.name
