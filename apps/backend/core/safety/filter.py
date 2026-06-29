"""Safety hook contracts.

The base implementation is intentionally transparent. Safety decisions are not
made by keyword tables in core code.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SafetyVerdict:
    """安全过滤判定结果。 """

    allowed: bool = True
    reason: str = ""
    redirect_node: Optional[str] = None
    replacement_text: str = ""
    matched_rules: List[str] = field(default_factory=list)
    safe_response: str = ""


class SafetyFilter(abc.ABC):
    """安全过滤抽象基类。"""

    @abc.abstractmethod
    async def pre_check(self, text: str, node: str = "") -> SafetyVerdict:
        """Pre-LLM 输入安全检查。"""

    @abc.abstractmethod
    async def post_filter(self, text: str) -> SafetyVerdict:
        """Post-LLM 输出安全过滤。"""


class BaseSafetyFilter(SafetyFilter):
    """Transparent default safety hook."""

    async def pre_check(self, text: str, node: str = "") -> SafetyVerdict:
        return SafetyVerdict(allowed=True)

    async def post_filter(self, text: str) -> SafetyVerdict:
        return SafetyVerdict(allowed=True)
