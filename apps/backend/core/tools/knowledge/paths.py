"""
领域知识路径工具

提供 audience 目录解析与路径边界校验，防止路径穿越攻击（../）。

目录结构：
    <repo_root>/audiences/{audience}/domain/

repo_root 推断：从本文件（core/tools/knowledge/paths.py）向上 4 层。
    paths.py → knowledge/ → tools/ → core/ → <repo_root>
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.tools.base import ToolExecutionError

# repo_root = <repo_root>，本文件位于 core/tools/knowledge/paths.py，向上 4 层即为项目根目录
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]


def get_domain_root(audience: str) -> Optional[Path]:
    """
    返回指定 audience 的领域知识目录路径。

    Args:
        audience: 人群标识（如 "Aini"）

    Returns:
        Path: 目录存在时返回绝对路径；目录不存在时返回 None。
    """
    domain_dir = _REPO_ROOT / "audiences" / audience / "domain"
    if domain_dir.is_dir():
        return domain_dir.resolve()
    return None


def safe_resolve(audience: str, relative_path: str) -> Path:
    """
    将相对路径拼接到 audience 的 domain 目录，并做边界校验。

    Args:
        audience:      人群标识（如 "Aini"）
        relative_path: 相对文件名（如 "失能老年人养老服务消费补贴.md"）

    Returns:
        Path: 通过边界校验的绝对路径

    Raises:
        ToolExecutionError: 路径越界（路径穿越攻击）或 domain 目录不存在
    """
    domain_root = get_domain_root(audience)
    if domain_root is None:
        raise ToolExecutionError(
            "safe_resolve",
            f"audience '{audience}' 没有配置领域知识库（目录不存在）",
        )

    # 拼接后 resolve，消除所有 ../ 等相对符号
    resolved = (domain_root / relative_path).resolve()

    # 边界校验：最终路径必须仍在 domain_root 下
    try:
        resolved.relative_to(domain_root)
    except ValueError:
        raise ToolExecutionError(
            "safe_resolve",
            f"路径越界：'{relative_path}' 超出了 audience '{audience}' 的领域目录范围，"
            "禁止跨 audience 访问",
        )

    return resolved
