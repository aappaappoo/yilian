"""LLM request trace logging.

This module records the full model request context for debugging routing,
tool-choice, and prompt accuracy issues. Logging failures must never affect
the request path.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from core.observability import current_span_id, current_trace_id


_SECRET_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "credential",
    "cookie",
    "set-cookie",
    "jwt",
}


def _enabled() -> bool:
    raw = os.environ.get("ENABLE_LLM_TRACE")
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _trace_dir() -> Path:
    return Path(os.environ.get("LLM_TRACE_DIR", "log/llm_traces"))


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in _SECRET_KEYS:
                result[key_text] = "[REDACTED]"
            else:
                result[key_text] = _json_safe(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=lambda item: str(item))]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _event_path(trace_id: str) -> Path:
    day = time.strftime("%Y%m%d", time.localtime())
    name = trace_id or f"unscoped-{day}"
    return _trace_dir() / day / f"{name}.jsonl"


def _write_event(event: dict[str, Any]) -> None:
    if not _enabled():
        return
    try:
        trace_id = str(event.get("trace_id") or "")
        path = _event_path(trace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_json_safe(event), ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception as exc:
        logger.warning(f"[llm_trace] 写入失败: {type(exc).__name__}: {exc}")


def record_llm_request(
    *,
    source: str,
    provider: str = "",
    model: str = "",
    base_url: str = "",
    payload: dict[str, Any],
    attributes: dict[str, Any] | None = None,
) -> str:
    """Record a full LLM request payload and return a call id."""
    call_id = str(uuid.uuid4())
    _write_event(
        {
            "type": "llm_request",
            "call_id": call_id,
            "trace_id": current_trace_id.get(),
            "span_id": current_span_id.get(),
            "timestamp": time.time(),
            "source": source,
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "attributes": dict(attributes or {}),
            "payload": payload,
        }
    )
    return call_id


def record_llm_response(
    *,
    call_id: str,
    source: str,
    provider: str = "",
    model: str = "",
    status: str = "success",
    response: Any = None,
    error: BaseException | None = None,
) -> None:
    """Record the model response or failure matching a previous call id."""
    event: dict[str, Any] = {
        "type": "llm_response",
        "call_id": call_id,
        "trace_id": current_trace_id.get(),
        "span_id": current_span_id.get(),
        "timestamp": time.time(),
        "source": source,
        "provider": provider,
        "model": model,
        "status": status,
        "response": response,
    }
    if error is not None:
        event["error_type"] = type(error).__name__
        event["error_message"] = str(error)
    _write_event(event)
