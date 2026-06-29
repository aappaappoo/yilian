#!/usr/bin/env python3
"""Soulbot command-line entry for companion checks."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "apps" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.soul_companion import answer_user_text  # noqa: E402
from core.soul_companion.skills import (  # noqa: E402
    inspect_skill_source,
    install_skill,
    list_installed_skills,
    set_skill_enabled,
    skills_root,
    uninstall_skill,
)


async def _run_query(query: str) -> int:
    result = await answer_user_text(query)
    print(result.text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Soulbot companion CLI")
    parser.add_argument("-q", "--query", help="single query to answer")
    subparsers = parser.add_subparsers(dest="command")

    skills_parser = subparsers.add_parser("skills", help="manage runtime skills")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_action")

    skills_subparsers.add_parser("list", help="list installed runtime skills")

    inspect_parser = skills_subparsers.add_parser("inspect", help="preview a skill before installing")
    inspect_parser.add_argument("source", help="local path, builtin/<name>, or direct HTTP(S) SKILL.md URL")
    inspect_parser.add_argument("--name", default="", help="override skill name")

    install_parser = skills_subparsers.add_parser("install", help="install a runtime skill")
    install_parser.add_argument("source", help="local path, builtin/<name>, or direct HTTP(S) SKILL.md URL")
    install_parser.add_argument("--name", default="", help="override skill name")
    install_parser.add_argument("--force", action="store_true", help="reinstall when already installed")

    uninstall_parser = skills_subparsers.add_parser("uninstall", help="remove an installed runtime skill")
    uninstall_parser.add_argument("name", help="skill name")

    enable_parser = skills_subparsers.add_parser("enable", help="enable an installed runtime skill")
    enable_parser.add_argument("name", help="skill name")

    disable_parser = skills_subparsers.add_parser("disable", help="disable an installed runtime skill")
    disable_parser.add_argument("name", help="skill name")

    args = parser.parse_args()

    if args.command == "skills":
        action = args.skills_action
        if action == "list":
            installed = list_installed_skills(include_disabled=True)
            print(f"skills_dir: {skills_root()}")
            if not installed:
                print("No runtime skills installed.")
                return 0
            for skill in installed:
                status = "enabled" if skill.enabled else "disabled"
                description = f" - {skill.description}" if skill.description else ""
                print(f"{skill.name}\t{status}\t{skill.source}{description}")
            return 0
        if action == "inspect":
            payload = inspect_skill_source(args.source, name=args.name)
            print(f"name: {payload['name']}")
            print(f"description: {payload['description']}")
            print("\npreview:")
            print(payload["preview"])
            return 0
        if action == "install":
            entry = install_skill(args.source, name=args.name, force=args.force)
            print(f"Installed runtime skill: {entry['name']}")
            print(f"path: {skills_root() / entry['path']}")
            return 0
        if action == "uninstall":
            removed = uninstall_skill(args.name)
            print(f"Removed runtime skill: {args.name}" if removed else f"Skill not installed: {args.name}")
            return 0
        if action == "enable":
            entry = set_skill_enabled(args.name, True)
            print(f"Enabled runtime skill: {entry['name']}")
            return 0
        if action == "disable":
            entry = set_skill_enabled(args.name, False)
            print(f"Disabled runtime skill: {entry['name']}")
            return 0
        skills_parser.error("请提供 skills 子命令：list / inspect / install / uninstall / enable / disable")

    if not args.query:
        parser.error("请使用 -q/--query 提供要查询的内容")
    return asyncio.run(_run_query(args.query))


if __name__ == "__main__":
    raise SystemExit(main())
