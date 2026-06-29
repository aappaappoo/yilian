#!/usr/bin/env python3
"""
领域知识索引自动生成工具

扫描 audiences/*/domain/*.md 文件，解析标题/文号/日期/章节等元数据，
为每个 audience 自动生成 _index.yaml 索引文件。

用法:
  # 扫描所有 audience，仅为缺少 _index.yaml 的生成
  python scripts/generate_domain_index.py

  # 指定单个 audience
  python scripts/generate_domain_index.py --audience Aini

  # 强制覆盖已有的 _index.yaml
  python scripts/generate_domain_index.py --force

  # 仅预览，不写入文件
  python scripts/generate_domain_index.py --dry-run

设计原则:
  - 每个 audience 独立隔离，互不影响
  - 项目初始化时执行一次即可
  - 新增 MD 文件后重新执行即可自动更新
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# 项目根目录（从 scripts/ 向上一层）
_REPO_ROOT = Path(__file__).resolve().parent.parent
_AUDIENCES_DIR = _REPO_ROOT / "audiences"

# 从 topics/summary 中排除的章节标题（通用附则、附录类标题）
_EXCLUDED_SECTION_TITLES = {"附则"}


# ─── Markdown 解析 ──────────────────────────────────────────


def parse_md_metadata(md_path: Path) -> Dict[str, Any]:
    """
    从单个 Markdown 文件中解析元数据。

    支持的格式:
      - 标题: 首行 `# 标题`
      - 文号: `**文号**：XXX号`
      - 日期: `**发布日期**：YYYY-MM-DD` 或 `（YYYY年MM月DD日）`
      - 主题词: `**主题词**：词1 词2`
      - 章节: `## 一、XXX` 级别的标题

    Returns:
        包含 file, title, doc_no, date, topics, sections, summary 的字典
    """
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = _parse_title(lines)
    doc_no = _parse_doc_no(lines)
    date = _parse_date(lines)
    keywords = _parse_keywords(lines)
    sections = _parse_sections(lines)
    summary = _build_summary(title, sections)

    # topics: 优先使用主题词，补充章节标题中的关键词
    topics = keywords if keywords else _extract_topics_from_sections(sections)

    return {
        "file": md_path.name,
        "title": title,
        "doc_no": doc_no,
        "date": date,
        "topics": topics,
        "summary": summary,
    }


def _parse_title(lines: List[str]) -> str:
    """解析 Markdown 一级标题 `# xxx`。"""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("#").strip()
    return ""


def _parse_doc_no(lines: List[str]) -> str:
    """
    解析文号，匹配 `**文号**：XXX` 格式。
    支持全角/半角冒号。
    """
    pattern = re.compile(r"\*\*文号\*\*\s*[：:]\s*(.+)")
    for line in lines:
        m = pattern.search(line.strip())
        if m:
            return m.group(1).strip()
    return ""


def _parse_date(lines: List[str]) -> str:
    """
    解析发布日期，支持两种格式:
      1. `**发布日期**：YYYY-MM-DD`
      2. `（YYYY年MM月DD日）`
    """
    # 格式 1: **发布日期**：YYYY-MM-DD
    date_field = re.compile(r"\*\*发布日期\*\*\s*[：:]\s*(\d{4}-\d{2}-\d{2})")
    for line in lines:
        m = date_field.search(line.strip())
        if m:
            return m.group(1)

    # 格式 2: （YYYY年MM月DD日）— 通常在标题后的前 5 行内
    cn_date = re.compile(r"[（(](\d{4})年(\d{1,2})月(\d{1,2})日[)）]")
    for line in lines[:10]:
        m = cn_date.search(line.strip())
        if m:
            y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
            return f"{y}-{mo}-{d}"

    return ""


def _parse_keywords(lines: List[str]) -> List[str]:
    """解析 `**主题词**：词1 词2` 或 `**主题词**：词1、词2`。"""
    pattern = re.compile(r"\*\*主题词\*\*\s*[：:]\s*(.+)")
    for line in lines:
        m = pattern.search(line.strip())
        if m:
            raw = m.group(1).strip()
            # 支持空格、顿号、逗号分隔
            parts = re.split(r"[、,，\s]+", raw)
            return [p.strip() for p in parts if p.strip()]
    return []


def _parse_sections(lines: List[str]) -> List[str]:
    """提取所有二级标题 `## xxx` 的文本内容。"""
    sections = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            section_text = stripped.lstrip("#").strip()
            sections.append(section_text)
    return sections


def _extract_topics_from_sections(sections: List[str]) -> List[str]:
    """从章节标题中提取关键词作为 topics（去除编号前缀）。"""
    topics = []
    # 去除 "一、" "二、" 等编号前缀
    num_prefix = re.compile(r"^[一二三四五六七八九十]+、\s*")
    for s in sections:
        cleaned = num_prefix.sub("", s).strip()
        if cleaned and cleaned not in _EXCLUDED_SECTION_TITLES:
            topics.append(cleaned)
    # 最多保留 5 个
    return topics[:5]


def _build_summary(title: str, sections: List[str]) -> str:
    """
    根据标题和章节标题自动生成简要摘要。

    格式: "《{title}》，主要包括：{section1}、{section2}…"
    """
    if not sections:
        return title

    # 去掉编号
    num_prefix = re.compile(r"^[一二三四五六七八九十]+、\s*")
    cleaned = [num_prefix.sub("", s).strip() for s in sections]
    cleaned = [c for c in cleaned if c and c not in _EXCLUDED_SECTION_TITLES]

    if not cleaned:
        return title

    joined = "、".join(cleaned[:5])
    if len(cleaned) > 5:
        joined += "等"
    return f"主要包括：{joined}。"


# ─── YAML 生成 ────────────────────────────────────────────


def _yaml_representer_str(dumper: yaml.Dumper, data: str) -> Any:
    """对含有特殊字符的字符串使用双引号。"""
    if not data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", "", style='"')
    # 包含中文括号、特殊符号时使用双引号
    if any(c in data for c in ("〔", "〕", "：", "《", "》", "\n")):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def generate_yaml(docs: List[Dict[str, Any]]) -> str:
    """将文档元数据列表序列化为 YAML 字符串。"""
    dumper = yaml.Dumper
    dumper.add_representer(str, _yaml_representer_str)

    output = yaml.dump(
        {"docs": docs},
        Dumper=dumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )
    return output


# ─── 主流程 ──────────────────────────────────────────────


def process_audience(audience_dir: Path, force: bool = False, dry_run: bool = False) -> Optional[str]:
    """
    处理单个 audience 目录。

    Args:
        audience_dir: audience 目录路径 (如 audiences/Aini/)
        force:        是否覆盖已有的 _index.yaml
        dry_run:      仅预览，不实际写入

    Returns:
        生成的 YAML 内容 (成功时) 或 None (跳过时)
    """
    audience_name = audience_dir.name
    domain_dir = audience_dir / "domain"

    if not domain_dir.is_dir():
        return None

    index_path = domain_dir / "_index.yaml"

    # 如果已有 _index.yaml 且未指定 --force，跳过
    if index_path.is_file() and not force:
        print(f"  ⏭  {audience_name}: _index.yaml 已存在，跳过（使用 --force 覆盖）")
        return None

    # 扫描 .md 文件
    md_files = sorted(domain_dir.glob("*.md"))
    if not md_files:
        print(f"  ⚠  {audience_name}: domain/ 目录下没有 .md 文件")
        return None

    # 解析每个 md 文件
    docs = []
    for md_file in md_files:
        meta = parse_md_metadata(md_file)
        docs.append(meta)
        print(f"     📄 {meta['file']}")
        print(f"        标题: {meta['title']}")
        if meta["doc_no"]:
            print(f"        文号: {meta['doc_no']}")
        if meta["date"]:
            print(f"        日期: {meta['date']}")

    yaml_content = generate_yaml(docs)

    if dry_run:
        print(f"\n  📋 {audience_name}/_index.yaml 预览:")
        print("  " + "-" * 60)
        for line in yaml_content.splitlines():
            print(f"  {line}")
        print("  " + "-" * 60)
    else:
        action = "覆盖" if index_path.is_file() else "生成"
        index_path.write_text(yaml_content, encoding="utf-8")
        print(f"  ✅ {audience_name}: 已{action} _index.yaml（{len(docs)} 个文档）")

    return yaml_content


def main() -> None:
    parser = argparse.ArgumentParser(
        description="自动扫描 audiences/*/domain/*.md 并生成 _index.yaml 索引",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/generate_domain_index.py                  # 扫描所有 audience
  python scripts/generate_domain_index.py --audience Aini  # 仅处理 Aini
  python scripts/generate_domain_index.py --force          # 强制覆盖
  python scripts/generate_domain_index.py --dry-run        # 仅预览
        """,
    )
    parser.add_argument(
        "--audience",
        type=str,
        default=None,
        help="指定要处理的 audience 名称（默认处理全部）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制覆盖已有的 _index.yaml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览生成结果，不写入文件",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  领域知识索引自动生成工具")
    print("=" * 60)

    if not _AUDIENCES_DIR.is_dir():
        print(f"❌ audiences 目录不存在: {_AUDIENCES_DIR}")
        sys.exit(1)

    # 确定要处理的 audience 列表
    if args.audience:
        target_dir = _AUDIENCES_DIR / args.audience
        if not target_dir.is_dir():
            print(f"❌ audience 目录不存在: {target_dir}")
            sys.exit(1)
        audience_dirs = [target_dir]
    else:
        audience_dirs = sorted(
            d for d in _AUDIENCES_DIR.iterdir()
            if d.is_dir() and not d.name.startswith("_") and d.name != "__pycache__"
        )

    total = 0
    generated = 0

    for audience_dir in audience_dirs:
        domain_dir = audience_dir / "domain"
        if not domain_dir.is_dir():
            continue

        total += 1
        print(f"\n📁 处理 audience: {audience_dir.name}")
        result = process_audience(audience_dir, force=args.force, dry_run=args.dry_run)
        if result is not None:
            generated += 1

    print(f"\n{'=' * 60}")
    print(f"  完成！扫描 {total} 个 audience，生成 {generated} 个 _index.yaml")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
