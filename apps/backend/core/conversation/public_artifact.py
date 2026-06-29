"""Frontend-safe task artifact projection.

Task artifacts can contain traces, model prompts, raw provider responses, and
other debug data. Keep those objects available inside the backend, but only
send a compact public view to browser clients.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

PUBLIC_ARTIFACT_MAX_DEPTH = 12
PUBLIC_ARTIFACT_MAX_DICT_KEYS = 80
PUBLIC_ARTIFACT_DEFAULT_LIST_LIMIT = 12

_FORBIDDEN_KEYS = {
    "diagnostics",
    "disclosure",
    "evidence",
    "final_validation",
    "input_snapshot",
    "llm_messages",
    "logs",
    "messages",
    "native_trace",
    "output_snapshot",
    "prompt",
    "raw",
    "raw_url",
    "raw_response",
    "request_url",
    "recovery_plans",
    "system_prompt",
    "trace",
    "validation",
    "api_key",
    "authorization",
}

_LIST_LIMITS = {
    "artifacts": 8,
    "cards": 12,
    "forecast": 10,
    "nodes": 12,
    "photos": 1,
    "poi_groups": 6,
    "pois": 12,
    "series": 100,
}

_STRING_LIMITS = {
    "address": 240,
    "content": 4_000,
    "note": 400,
    "reply": 6_000,
    "summary": 600,
    "text": 6_000,
    "tts_text": 2_000,
    "url": 1_000,
    "website": 1_000,
}

_PROGRESS_TEXT_FIELDS = {
    "description",
    "error_reason",
    "name",
    "phase_label",
    "retry_reason",
    "summary",
    "title",
}

_PROGRESS_DEBUG_FIELDS = {
    "action",
    "frame",
    "frame_meta",
    "run_state",
    "trace",
    "_history_last_monotonic",
    "_history_started_monotonic",
}

_PROGRESS_HISTORY_TEXT_FIELDS = {
    "description",
    "phase_label",
}

_PROGRESS_HISTORY_NUMERIC_FIELDS = {
    "attempt",
    "duration_ms",
    "elapsed_ms",
    "phase_count",
    "phase_index",
    "progress",
}

_ID_FIELD_PATTERN = re.compile(
    r"(?i)\b(?:task|run|request|ref|call|session|speak|user)[_-]?id\b\s*[:=]\s*['\"]?[-\w]{6,}['\"]?"
)
_UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


def public_artifact(artifact: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """Return a compact artifact projection that is safe to send to browsers."""
    if not isinstance(artifact, Mapping):
        return None
    value = _sanitize_mapping(artifact, depth=0)
    return value if value else None


def public_task_progress_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize artifact fields inside a task_progress payload."""
    safe_payload = dict(payload)
    tasks = safe_payload.get("tasks")
    if not isinstance(tasks, list):
        return safe_payload

    safe_tasks: list[Any] = []
    for item in tasks:
        if not isinstance(item, Mapping):
            safe_tasks.append(item)
            continue
        safe_item = dict(item)
        for key in _PROGRESS_DEBUG_FIELDS:
            safe_item.pop(key, None)
        safe_artifact = public_artifact(safe_item.get("artifact"))
        if safe_artifact:
            safe_item["artifact"] = safe_artifact
        else:
            safe_item.pop("artifact", None)
        status = str(safe_item.get("status") or "")
        for key in _PROGRESS_TEXT_FIELDS:
            if key not in safe_item:
                continue
            cleaned = _public_progress_text(safe_item.get(key), status=status, field=key)
            if cleaned:
                safe_item[key] = cleaned
            else:
                safe_item.pop(key, None)
        if not str(safe_item.get("description") or "").strip():
            safe_item["description"] = _default_progress_description(status)
        if not str(safe_item.get("phase_label") or "").strip():
            safe_item["phase_label"] = safe_item["description"]
        safe_history = _public_progress_history(safe_item.get("history"), status=status)
        if safe_history:
            safe_item["history"] = safe_history
        else:
            safe_item.pop("history", None)
        safe_tasks.append(safe_item)
    safe_payload["tasks"] = safe_tasks
    return safe_payload


def _public_progress_history(raw: Any, *, status: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in raw[-40:]:
        if not isinstance(entry, Mapping):
            continue
        safe: dict[str, Any] = {}
        phase_key = str(entry.get("phase_key") or "").strip()
        if phase_key:
            safe["phase_key"] = phase_key[:160]
        entry_status = str(entry.get("status") or status).strip()
        if entry_status:
            safe["status"] = entry_status[:40]
        for key in _PROGRESS_HISTORY_TEXT_FIELDS:
            cleaned = _public_progress_text(entry.get(key), status=entry_status or status, field=key)
            if cleaned:
                safe[key] = cleaned
        for key in _PROGRESS_HISTORY_NUMERIC_FIELDS:
            value = entry.get(key)
            if isinstance(value, (int, float)):
                safe[key] = max(0, int(round(value)))
        if safe.get("phase_key") or safe.get("phase_label") or safe.get("description"):
            items.append(safe)
    return items


def _sanitize_mapping(
    source: Mapping[str, Any],
    *,
    depth: int,
) -> dict[str, Any]:
    if depth >= PUBLIC_ARTIFACT_MAX_DEPTH:
        return {}

    result: dict[str, Any] = {}
    for raw_key, raw_value in list(source.items())[:PUBLIC_ARTIFACT_MAX_DICT_KEYS]:
        key = str(raw_key)
        normalized = key.lower()
        if normalized in _FORBIDDEN_KEYS:
            continue
        if normalized == "draft":
            value = _sanitize_draft(raw_value, depth=depth + 1)
        else:
            value = _sanitize_value(raw_value, key=normalized, depth=depth + 1)
        if value not in (None, "", [], {}):
            result[key] = value
    return result


def _sanitize_draft(value: Any, *, depth: int) -> Optional[dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in ("status", "response_policy", "summary", "reply"):
        if key in value:
            safe_value = _sanitize_value(value[key], key=key, depth=depth + 1)
            if safe_value not in (None, "", [], {}):
                result[key] = safe_value
    for key in ("nodes", "artifacts"):
        if key in value:
            safe_value = _sanitize_value(value[key], key=key, depth=depth + 1)
            if safe_value not in (None, "", [], {}):
                result[key] = safe_value
    return result or None


def _sanitize_value(value: Any, *, key: str, depth: int) -> Any:
    if depth >= PUBLIC_ARTIFACT_MAX_DEPTH:
        return None
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, depth=depth)
    if isinstance(value, list):
        limit = _LIST_LIMITS.get(key, PUBLIC_ARTIFACT_DEFAULT_LIST_LIMIT)
        return [
            safe_item
            for item in value[:limit]
            if (safe_item := _sanitize_value(item, key=key, depth=depth + 1)) not in (None, "", [], {})
        ]
    if isinstance(value, str):
        return _truncate_string(value, key=key)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _truncate_string(str(value), key=key)


def _truncate_string(value: str, *, key: str) -> str:
    limit = _STRING_LIMITS.get(key, 1_000)
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _public_progress_text(value: Any, *, status: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _looks_like_internal_progress_text(text):
        return "" if field == "name" else _default_progress_description(status)
    text = _ID_FIELD_PATTERN.sub("", text)
    text = _UUID_PATTERN.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,，;；")
    if not text:
        return "" if field == "name" else _default_progress_description(status)
    return _truncate_string(text, key=field)


def _looks_like_internal_progress_text(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    if stripped.startswith("{") and stripped.endswith("}") and any(
        key in lowered for key in ("request_id", "run_id", "task_id", "frame_trace_decider")
    ):
        return True
    if any(key in lowered for key in ("request_id", "run_id", "task_id", "ref_task_id")):
        return True
    return False


def _default_progress_description(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"queued", "pending"}:
        return "已理解你的需求，正在安排下一步。"
    if normalized in {"running", "in_progress", "processing"}:
        return "正在执行当前动作。"
    if normalized == "need_input":
        return "需要你补充信息后继续。"
    if normalized == "success":
        return "动作已完成，正在整理回复。"
    if normalized in {"failed", "timeout"}:
        return "当前动作执行失败。"
    if normalized in {"cancelled", "canceled"}:
        return "当前任务已停止。"
    return "Aini 正在处理任务。"
