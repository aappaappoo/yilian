"""Runtime skill installation and prompt loading for Soul companion."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Mapping, Optional

import yaml

from core.config import settings


_SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_LOCK_FILE = "skills-lock.json"
_DISABLED_FILE = ".disabled"
_MAX_URL_SKILL_BYTES = 512 * 1024
_FINAL_REPLY_SCOPE = "final_reply"
_LINKED_FILE_GROUPS = ("references", "templates", "scripts", "assets")


@dataclass(frozen=True)
class SoulSkill:
    name: str
    description: str
    path: Path
    content: str
    frontmatter: Mapping[str, Any]
    enabled: bool = True
    source: str = "local"


@dataclass(frozen=True)
class SoulSkillPrompt:
    prompt: str
    active_skills: list[str]


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists():
            return parent
    for parent in current.parents:
        if (parent / "main.py").exists() and (parent / "core").is_dir():
            return parent
        if (parent / "apps" / "backend").is_dir():
            return parent
    return Path.cwd().resolve()


def skills_root() -> Path:
    configured = Path(settings.soul_skills_dir).expanduser()
    if configured.is_absolute():
        return configured
    return (_repo_root() / configured).resolve()


def builtin_skills_root() -> Path:
    return Path(__file__).resolve().parent / "builtin_skills"


def _lock_path() -> Path:
    return skills_root() / _LOCK_FILE


def _load_lock() -> dict[str, Any]:
    path = _lock_path()
    if not path.exists():
        return {"version": 1, "skills": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "skills": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "skills": {}}
    skills = payload.get("skills")
    if not isinstance(skills, dict):
        payload["skills"] = {}
    payload.setdefault("version", 1)
    return payload


def _write_lock(payload: Mapping[str, Any]) -> None:
    root = skills_root()
    root.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(root),
        prefix=".skills-lock-",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    tmp_path.replace(_lock_path())


def _parse_skill_markdown(content: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content
    try:
        parsed = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return parsed, content[match.end():]


def _normalize_skill_name(raw: str) -> str:
    name = str(raw or "").strip().lower().replace(" ", "-")
    name = re.sub(r"[^a-z0-9_-]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-_")
    if not name or not _SKILL_NAME_RE.match(name):
        raise ValueError(
            "Invalid skill name. Use 1-64 chars: lowercase letters, digits, '-' or '_', starting with a letter."
        )
    return name


def _skill_name_from_content(content: str, fallback: str = "") -> str:
    frontmatter, _body = _parse_skill_markdown(content)
    return _normalize_skill_name(frontmatter.get("name") or fallback)


def _skill_description(frontmatter: Mapping[str, Any], body: str) -> str:
    description = str(frontmatter.get("description") or "").strip()
    if description:
        return " ".join(description.split())
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return " ".join(line.split())[:180]
    return ""


def _iter_values(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return []


def _soulbot_metadata(frontmatter: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = frontmatter.get("metadata")
    if not isinstance(metadata, Mapping):
        return {}
    soulbot = metadata.get("soulbot")
    return soulbot if isinstance(soulbot, Mapping) else {}


def _skill_scope(frontmatter: Mapping[str, Any]) -> str:
    return str(_soulbot_metadata(frontmatter).get("scope") or "").strip().lower()


def _is_final_reply_skill(skill: SoulSkill) -> bool:
    return skill.name == "reply-humanizer" or _skill_scope(skill.frontmatter) == _FINAL_REPLY_SCOPE


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _dir_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if not item.is_file() or item.is_symlink():
            continue
        hasher.update(str(item.relative_to(path)).encode("utf-8"))
        hasher.update(item.read_bytes())
    return hasher.hexdigest()


def _safe_skill_dir(name: str) -> Path:
    root = skills_root().resolve()
    candidate = (root / name).resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError("Unsafe skill destination path")
    return candidate


def _copy_skill_dir_safe(source_dir: Path, dest_dir: Path) -> None:
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in source_dir.rglob("*"):
        if item.is_symlink():
            continue
        rel = item.relative_to(source_dir)
        if any(part in {"", ".", ".."} for part in rel.parts):
            continue
        target = dest_dir / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _download_url_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Soulbot-Skill-Installer/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > _MAX_URL_SKILL_BYTES:
                raise ValueError("Remote skill is too large")
            data = response.read(_MAX_URL_SKILL_BYTES + 1)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to download skill: {exc}") from exc
    if len(data) > _MAX_URL_SKILL_BYTES:
        raise ValueError("Remote skill is too large")
    return data.decode("utf-8")


def _resolve_builtin_source(raw_source: str) -> Optional[Path]:
    prefixes = ("builtin/", "official/")
    if not raw_source.startswith(prefixes):
        return None
    _prefix, _sep, name = raw_source.partition("/")
    skill_name = _normalize_skill_name(name)
    candidate = (builtin_skills_root() / skill_name).resolve()
    root = builtin_skills_root().resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError("Unsafe builtin skill path")
    if not (candidate / "SKILL.md").exists():
        raise FileNotFoundError(f"Builtin skill not found: {raw_source}")
    return candidate


def install_skill(
    source: str,
    *,
    name: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """Install a runtime skill from a local path or direct HTTP(S) SKILL.md URL."""
    raw_source = str(source or "").strip()
    if not raw_source:
        raise ValueError("Skill source is required")

    root = skills_root()
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    builtin_source = _resolve_builtin_source(raw_source)

    if builtin_source is not None:
        content = (builtin_source / "SKILL.md").read_text(encoding="utf-8")
        skill_name = _normalize_skill_name(name) if name else _skill_name_from_content(content, builtin_source.name)
        dest_dir = _safe_skill_dir(skill_name)
        if dest_dir.exists() and not force:
            raise FileExistsError(f"Skill '{skill_name}' is already installed. Use --force to reinstall.")
        _copy_skill_dir_safe(builtin_source, dest_dir)
        source_type = "builtin"
        digest = _dir_hash(dest_dir)
    elif raw_source.startswith(("http://", "https://")):
        content = _download_url_text(raw_source)
        skill_name = _normalize_skill_name(name) if name else _skill_name_from_content(content, Path(raw_source).stem)
        dest_dir = _safe_skill_dir(skill_name)
        if dest_dir.exists() and not force:
            raise FileExistsError(f"Skill '{skill_name}' is already installed. Use --force to reinstall.")
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "SKILL.md").write_text(content, encoding="utf-8")
        source_type = "url"
        digest = _content_hash(content)
    else:
        source_path = Path(raw_source).expanduser()
        if not source_path.is_absolute():
            source_path = (_repo_root() / source_path).resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Skill source not found: {source_path}")
        if source_path.is_dir():
            skill_md = source_path / "SKILL.md"
            if not skill_md.exists():
                raise FileNotFoundError(f"Missing SKILL.md in {source_path}")
            content = skill_md.read_text(encoding="utf-8")
            skill_name = _normalize_skill_name(name) if name else _skill_name_from_content(content, source_path.name)
            dest_dir = _safe_skill_dir(skill_name)
            if dest_dir.exists() and not force:
                raise FileExistsError(f"Skill '{skill_name}' is already installed. Use --force to reinstall.")
            _copy_skill_dir_safe(source_path, dest_dir)
            source_type = "local_dir"
            digest = _dir_hash(dest_dir)
        else:
            if source_path.name != "SKILL.md" and source_path.suffix.lower() not in {".md", ".txt"}:
                raise ValueError("Local file installs must point to SKILL.md or a markdown/text file")
            content = source_path.read_text(encoding="utf-8")
            skill_name = _normalize_skill_name(name) if name else _skill_name_from_content(content, source_path.stem)
            dest_dir = _safe_skill_dir(skill_name)
            if dest_dir.exists() and not force:
                raise FileExistsError(f"Skill '{skill_name}' is already installed. Use --force to reinstall.")
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / "SKILL.md").write_text(content, encoding="utf-8")
            source_type = "local_file"
            digest = _content_hash(content)

    lock = _load_lock()
    skills = lock.setdefault("skills", {})
    skills[skill_name] = {
        "name": skill_name,
        "source": raw_source,
        "source_type": source_type,
        "path": str(dest_dir.relative_to(root)),
        "enabled": True,
        "installed_at": now,
        "content_hash": digest,
    }
    _write_lock(lock)
    return dict(skills[skill_name])


def uninstall_skill(name: str) -> bool:
    skill_name = _normalize_skill_name(name)
    dest_dir = _safe_skill_dir(skill_name)
    removed = False
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
        removed = True
    lock = _load_lock()
    skills = lock.setdefault("skills", {})
    if skill_name in skills:
        del skills[skill_name]
        removed = True
    _write_lock(lock)
    return removed


def set_skill_enabled(name: str, enabled: bool) -> dict[str, Any]:
    skill_name = _normalize_skill_name(name)
    dest_dir = _safe_skill_dir(skill_name)
    if not (dest_dir / "SKILL.md").exists():
        raise FileNotFoundError(f"Skill '{skill_name}' is not installed")
    marker = dest_dir / _DISABLED_FILE
    if enabled:
        marker.unlink(missing_ok=True)
    else:
        marker.write_text("disabled\n", encoding="utf-8")
    lock = _load_lock()
    skills = lock.setdefault("skills", {})
    entry = skills.setdefault(
        skill_name,
        {
            "name": skill_name,
            "source": "manual",
            "source_type": "manual",
            "path": skill_name,
            "installed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    entry["enabled"] = bool(enabled)
    _write_lock(lock)
    return dict(entry)


def list_installed_skills(*, include_disabled: bool = True) -> list[SoulSkill]:
    root = skills_root()
    if not root.exists():
        return []
    lock = _load_lock()
    lock_skills = lock.get("skills") if isinstance(lock.get("skills"), dict) else {}
    result: list[SoulSkill] = []
    for skill_md in sorted(root.rglob("SKILL.md")):
        if _LOCK_FILE in skill_md.parts:
            continue
        try:
            skill_dir = skill_md.parent
            content = skill_md.read_text(encoding="utf-8")
            frontmatter, body = _parse_skill_markdown(content)
            fallback = skill_dir.name
            name = _skill_name_from_content(content, fallback)
            lock_entry = lock_skills.get(name, {}) if isinstance(lock_skills, dict) else {}
            enabled = not (skill_dir / _DISABLED_FILE).exists()
            if isinstance(lock_entry, Mapping) and "enabled" in lock_entry:
                enabled = bool(lock_entry.get("enabled"))
            if not enabled and not include_disabled:
                continue
            result.append(
                SoulSkill(
                    name=name,
                    description=_skill_description(frontmatter, body),
                    path=skill_dir,
                    content=content.strip(),
                    frontmatter=frontmatter,
                    enabled=enabled,
                    source=str(lock_entry.get("source") or "manual") if isinstance(lock_entry, Mapping) else "manual",
                )
            )
        except Exception:
            continue
    return result


def inspect_skill_source(source: str, *, name: str = "") -> dict[str, Any]:
    raw_source = str(source or "").strip()
    builtin_source = _resolve_builtin_source(raw_source)
    if builtin_source is not None:
        content = (builtin_source / "SKILL.md").read_text(encoding="utf-8")
        fallback = builtin_source.name
    elif raw_source.startswith(("http://", "https://")):
        content = _download_url_text(raw_source)
        fallback = Path(raw_source).stem
    else:
        source_path = Path(raw_source).expanduser()
        if not source_path.is_absolute():
            source_path = (_repo_root() / source_path).resolve()
        if source_path.is_dir():
            content = (source_path / "SKILL.md").read_text(encoding="utf-8")
            fallback = source_path.name
        else:
            content = source_path.read_text(encoding="utf-8")
            fallback = source_path.stem
    frontmatter, body = _parse_skill_markdown(content)
    skill_name = _normalize_skill_name(name) if name else _skill_name_from_content(content, fallback)
    return {
        "name": skill_name,
        "description": _skill_description(frontmatter, body),
        "frontmatter": frontmatter,
        "preview": "\n".join(content.splitlines()[:80]),
    }


def _required_tools(skill: SoulSkill) -> set[str]:
    required_tools = set(_iter_values(skill.frontmatter.get("requires_tools")))
    soulbot = _soulbot_metadata(skill.frontmatter)
    required_tools.update(_iter_values(soulbot.get("requires_tools")))
    return required_tools


def _visible_runtime_skills(
    *,
    available_tools: Optional[Iterable[str]] = None,
) -> list[SoulSkill]:
    installed = list_installed_skills(include_disabled=False)
    if not installed:
        return []

    available_tool_set = (
        {str(item) for item in available_tools}
        if available_tools is not None
        else None
    )
    visible: list[SoulSkill] = []
    for skill in installed:
        if _is_final_reply_skill(skill):
            continue
        required_tools = _required_tools(skill)
        if (
            required_tools
            and available_tool_set is not None
            and not required_tools.issubset(available_tool_set)
        ):
            continue
        visible.append(skill)
    return visible


def build_soul_skill_index_prompt(
    *,
    available_tools: Optional[Iterable[str]] = None,
) -> SoulSkillPrompt:
    if not settings.soul_skills_enabled:
        return SoulSkillPrompt(prompt="", active_skills=[])

    available_tool_list = list(available_tools) if available_tools is not None else None
    available_tool_set = (
        {str(item) for item in available_tool_list}
        if available_tool_list is not None
        else None
    )
    if available_tool_set is not None and "skill_view" not in available_tool_set:
        return SoulSkillPrompt(prompt="", active_skills=[])

    visible = _visible_runtime_skills(available_tools=available_tool_list)

    if not visible:
        return SoulSkillPrompt(prompt="", active_skills=[])

    lines = [
        "## 已安装 Soulbot Skills",
        "下面是当前可用的 Soulbot skills。skills 是任务流程、领域规则和操作说明，不是最终答案。",
        "回答前请检查这些 skills 是否与用户任务相关。",
        "如果某个 skill 与当前任务相关，必须先调用 tool `skill_view(name)` 加载主说明，再继续执行。",
        "如果主说明返回 linked_files，且其中某个 reference/template/script 与当前任务相关，可继续调用 `skill_view(name, file_path)` 按需加载。",
        "`skill_view` 只用于加载 skill 说明或支持文件，不会执行用户任务。加载后，请根据 skill 内容决定是否继续调用业务 tools。",
        "",
        "<available_skills>",
    ]
    for skill in visible:
        description = f": {skill.description}" if skill.description else ""
        lines.append(f"- {skill.name}{description}")
    lines.extend(
        [
            "</available_skills>",
            "",
            "如果没有任何 skill 相关，可以不调用 `skill_view`，直接继续。",
        ]
    )

    return SoulSkillPrompt(prompt="\n".join(lines).strip(), active_skills=[])


def _validate_skill_view_name(name: str) -> str:
    raw = str(name or "").strip().lower().replace(" ", "-")
    if not raw:
        raise ValueError("skill name is required")
    if not _SKILL_NAME_RE.match(raw):
        raise ValueError(
            "Invalid skill name. Use lowercase letters, digits, '-' or '_', starting with a letter."
        )
    return raw


def _linked_skill_files(skill_dir: Path) -> dict[str, list[str]]:
    linked: dict[str, list[str]] = {group: [] for group in _LINKED_FILE_GROUPS}
    linked["files"] = []
    for item in sorted(skill_dir.rglob("*")):
        if not item.is_file() or item.is_symlink():
            continue
        rel = item.relative_to(skill_dir)
        if rel.name in {"SKILL.md", _DISABLED_FILE, _LOCK_FILE}:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        rel_text = rel.as_posix()
        group = rel.parts[0] if rel.parts and rel.parts[0] in _LINKED_FILE_GROUPS else "files"
        linked.setdefault(group, []).append(rel_text)
    return {group: files for group, files in linked.items() if files}


def _resolve_skill_support_file(skill_dir: Path, file_path: str) -> Path:
    raw = str(file_path or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("file_path is required when provided")
    if Path(raw).is_absolute() or PureWindowsPath(raw).is_absolute() or PureWindowsPath(raw).drive:
        raise ValueError("file_path must be a relative path within the skill directory")
    rel = Path(raw)
    if any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError("file_path cannot contain empty, '.', or '..' path segments")
    if rel.name in {_DISABLED_FILE, _LOCK_FILE} or any(part.startswith(".") for part in rel.parts):
        raise ValueError("file_path cannot read hidden skill metadata files")

    root = skill_dir.resolve()
    candidate = (skill_dir / rel).resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError("file_path must stay within the skill directory")
    if candidate.is_symlink():
        raise ValueError("file_path cannot read symlinks")
    if not candidate.is_file():
        raise FileNotFoundError(f"Skill support file not found: {raw}")
    return candidate


def view_soul_skill(
    name: str,
    *,
    file_path: Optional[str] = None,
    available_tools: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    if not settings.soul_skills_enabled:
        return {"success": False, "error": "Soulbot runtime skills are disabled."}

    try:
        lookup = _validate_skill_view_name(name)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    visible = _visible_runtime_skills(available_tools=available_tools)
    matches = [
        skill
        for skill in visible
        if skill.name == lookup or skill.path.name.lower() == lookup
    ]
    if not matches:
        return {
            "success": False,
            "error": f"Skill '{lookup}' not found.",
            "available_skills": [skill.name for skill in visible],
        }
    if len(matches) > 1:
        return {
            "success": False,
            "error": f"Ambiguous skill name '{lookup}'.",
            "matches": [str(skill.path) for skill in matches],
        }

    skill = matches[0]
    if file_path:
        try:
            support_file = _resolve_skill_support_file(skill.path, file_path)
        except (ValueError, FileNotFoundError) as exc:
            return {"success": False, "name": skill.name, "error": str(exc)}
        return {
            "success": True,
            "name": skill.name,
            "description": skill.description,
            "file_path": support_file.relative_to(skill.path).as_posix(),
            "content": support_file.read_text(encoding="utf-8").strip(),
            "path": str(support_file),
        }

    return {
        "success": True,
        "name": skill.name,
        "description": skill.description,
        "content": skill.content,
        "path": str(skill.path / "SKILL.md"),
        "linked_files": _linked_skill_files(skill.path),
    }


def build_reply_humanizer_prompt() -> SoulSkillPrompt:
    if not settings.soul_reply_humanizer_enabled:
        return SoulSkillPrompt(prompt="", active_skills=[])
    if not settings.soul_skills_enabled:
        return SoulSkillPrompt(prompt="", active_skills=[])

    final_skills = [
        skill for skill in list_installed_skills(include_disabled=False)
        if _is_final_reply_skill(skill)
    ]
    if not final_skills:
        return SoulSkillPrompt(prompt="", active_skills=[])

    max_chars = max(500, int(settings.soul_skills_max_prompt_chars))
    lines = [
        "## 最终回复风格规则",
        "以下 skill 只用于最终可见回复的表达风格。不要改变事实、工具结果、来源、健康边界或用户意图；不要因这些规则改变工具选择或工具参数。",
    ]
    active_names: list[str] = []
    budget = max_chars
    for skill in final_skills:
        active_names.append(skill.name)
        content = skill.content
        if len(content) > budget:
            content = content[:budget].rstrip() + "\n...[truncated]"
        lines.append("")
        lines.append(f"### Skill: {skill.name}")
        lines.append(content)
        budget -= len(content)
        if budget <= 0:
            break
    return SoulSkillPrompt(prompt="\n".join(lines).strip(), active_skills=active_names)
