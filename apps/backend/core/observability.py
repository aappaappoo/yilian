"""Lightweight task trace store for task-chain debugging and replay."""
from __future__ import annotations

import contextvars
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from loguru import logger


current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_trace_id", default="")
current_span_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_span_id", default="")


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
    "dashscope_api_key",
    "livekit_api_secret",
    "turn_credential",
}
_MAX_STRING_LEN = 4000


@dataclass
class TraceSpan:
    span_id: str = ""
    trace_id: str = ""
    parent_span_id: str = ""
    name: str = ""
    kind: str = "system"
    status: str = "running"
    started_at: float = 0.0
    ended_at: float | None = None
    duration_ms: float | None = None
    session_id: str = ""
    task_id: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    error_message: str = ""


@dataclass
class TraceRun:
    trace_id: str = ""
    root_span_id: str = ""
    session_id: str = ""
    task_id: str = ""
    audience: str = ""
    source: str = ""
    status: str = "running"
    started_at: float = 0.0
    ended_at: float | None = None
    duration_ms: float | None = None
    error_type: str = ""
    error_message: str = ""


def sanitize(value: Any) -> Any:
    """Return a redacted, JSON-safe copy of *value* without mutating inputs."""
    if is_dataclass(value):
        return sanitize(asdict(value))
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in _SECRET_KEYS:
                result[key] = "[REDACTED]"
            else:
                result[key] = sanitize(item)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, set):
        return [sanitize(item) for item in sorted(value, key=lambda item: str(item))]
    if isinstance(value, str):
        return value[:_MAX_STRING_LEN] if len(value) > _MAX_STRING_LEN else value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_MAX_STRING_LEN]


class InMemoryTraceStore:
    def __init__(self) -> None:
        self.events: dict[str, list[dict[str, Any]]] = {}

    def append_event(self, trace_id: str, event: dict[str, Any]) -> None:
        self.events.setdefault(trace_id, []).append(sanitize(event))

    def read_events(self, trace_id: str) -> list[dict[str, Any]]:
        return list(self.events.get(trace_id, []))


class JsonlTraceStore:
    def __init__(self, base_dir: str | os.PathLike[str] = "log/traces") -> None:
        self._base_dir = Path(base_dir)

    def append_event(self, trace_id: str, event: dict[str, Any]) -> None:
        day = time.strftime("%Y%m%d", time.localtime())
        path = self._base_dir / day / f"{trace_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(sanitize(event), ensure_ascii=False, separators=(",", ":")) + "\n")

    def read_events(self, trace_id: str) -> list[dict[str, Any]]:
        paths = sorted(self._base_dir.glob(f"*/{trace_id}.jsonl"))
        events: list[dict[str, Any]] = []
        for path in paths:
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        events.append(json.loads(line))
            except Exception as exc:
                logger.warning(f"Trace store read failed: trace_id={trace_id}, path={path}, error={exc}")
        return events


class _NullSpanContext:
    async def __aenter__(self) -> TraceSpan:
        return TraceSpan()

    async def __aexit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        return False


class _SpanContext:
    def __init__(
        self,
        recorder: "TraceRecorder",
        *,
        name: str,
        kind: str,
        trace_id: str,
        parent_span_id: str,
        session_id: str,
        task_id: str,
        attributes: dict[str, Any] | None,
        input_summary: dict[str, Any] | None,
    ) -> None:
        self._recorder = recorder
        self._span = TraceSpan(
            span_id=str(uuid.uuid4()),
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            status="running",
            started_at=time.time(),
            session_id=session_id,
            task_id=task_id,
            attributes=dict(attributes or {}),
            input_summary=dict(input_summary or {}),
        )
        self._trace_token: contextvars.Token[str] | None = None
        self._span_token: contextvars.Token[str] | None = None

    async def __aenter__(self) -> TraceSpan:
        self._trace_token = current_trace_id.set(self._span.trace_id)
        self._span_token = current_span_id.set(self._span.span_id)
        self._recorder._on_span_start(self._span)
        return self._span

    async def __aexit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        if exc is not None:
            self._span.status = "failed"
            self._span.error_type = type(exc).__name__
            self._span.error_message = str(exc)
        elif self._span.status == "running":
            self._span.status = "success"
        self._span.ended_at = time.time()
        self._span.duration_ms = max(0.0, (self._span.ended_at - self._span.started_at) * 1000)
        self._recorder._on_span_end(self._span)
        if self._span_token is not None:
            current_span_id.reset(self._span_token)
        if self._trace_token is not None:
            current_trace_id.reset(self._trace_token)
        return False


class TraceRecorder:
    def __init__(self, store: Any | None = None) -> None:
        self._store = store or JsonlTraceStore()
        self._runs: dict[str, TraceRun] = {}
        self._root_spans: dict[str, TraceSpan] = {}

    def start_trace(
        self,
        source: str,
        session_id: str = "",
        task_id: str = "",
        audience: str = "",
        attributes: dict | None = None,
    ) -> dict:
        trace_id = str(uuid.uuid4())
        root_span_id = str(uuid.uuid4())
        now = time.time()
        run = TraceRun(
            trace_id=trace_id,
            root_span_id=root_span_id,
            session_id=session_id,
            task_id=task_id,
            audience=audience,
            source=source,
            status="running",
            started_at=now,
        )
        root = TraceSpan(
            span_id=root_span_id,
            trace_id=trace_id,
            parent_span_id="",
            name="conversation.user_turn",
            kind="conversation",
            status="running",
            started_at=now,
            session_id=session_id,
            task_id=task_id,
            attributes=dict(attributes or {}),
        )
        self._runs[trace_id] = run
        self._root_spans[trace_id] = root
        current_trace_id.set(trace_id)
        current_span_id.set(root_span_id)
        self._append(trace_id, {"type": "run_start", "run": asdict(run)})
        self._append(trace_id, {"type": "span_start", "span": asdict(root)})
        return {
            "trace_id": trace_id,
            "parent_span_id": root_span_id,
            "root_span_id": root_span_id,
            "source": source,
        }

    def current_trace_context(self) -> dict:
        return {
            "trace_id": current_trace_id.get(),
            "parent_span_id": current_span_id.get(),
        }

    def span(
        self,
        name: str,
        kind: str = "system",
        trace_id: str = "",
        parent_span_id: str = "",
        session_id: str = "",
        task_id: str = "",
        attributes: dict | None = None,
        input_summary: dict | None = None,
    ) -> _SpanContext | _NullSpanContext:
        resolved_trace_id = trace_id or current_trace_id.get()
        if not resolved_trace_id:
            return _NullSpanContext()
        return _SpanContext(
            self,
            name=name,
            kind=kind,
            trace_id=resolved_trace_id,
            parent_span_id=parent_span_id or current_span_id.get(),
            session_id=session_id,
            task_id=task_id,
            attributes=attributes,
            input_summary=input_summary,
        )

    def finish_trace(self, trace_id: str, status: str = "success", error: Any = None) -> None:
        if not trace_id:
            return
        run = self._runs.get(trace_id) or self._load_run(trace_id)
        if run is None:
            return
        run.status = status
        if error is not None:
            run.error_type, run.error_message = _error_details(error)
        run.ended_at = time.time()
        run.duration_ms = max(0.0, (run.ended_at - run.started_at) * 1000)
        root = self._root_spans.get(trace_id) or self._load_root_span(trace_id)
        if root is not None and root.ended_at is None:
            root.status = "failed" if status == "failed" else "success"
            root.error_type = run.error_type
            root.error_message = run.error_message
            root.ended_at = run.ended_at
            root.duration_ms = max(0.0, (root.ended_at - root.started_at) * 1000)
            self._append(trace_id, {"type": "span_end", "span": asdict(root)})
        self._append(trace_id, {"type": "run_end", "run": asdict(run)})
        if current_trace_id.get() == trace_id:
            current_trace_id.set("")
            current_span_id.set("")

    def get_trace_tree(self, trace_id: str) -> dict:
        events = self._read_events(trace_id)
        run: dict[str, Any] = {}
        spans: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for event in events:
            event_type = event.get("type")
            if event_type in {"run_start", "run_end"} and isinstance(event.get("run"), dict):
                run.update(event["run"])
            if event_type in {"span_start", "span_end"} and isinstance(event.get("span"), dict):
                span = event["span"]
                span_id = str(span.get("span_id") or "")
                if not span_id:
                    continue
                if span_id not in spans:
                    order.append(span_id)
                    spans[span_id] = {}
                spans[span_id].update(span)

        nodes = {
            span_id: {"span": span, "children": []}
            for span_id, span in spans.items()
        }
        roots: list[dict[str, Any]] = []
        for span_id in order:
            node = nodes[span_id]
            parent_id = str(node["span"].get("parent_span_id") or "")
            parent = nodes.get(parent_id)
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)

        root_node = nodes.get(str(run.get("root_span_id") or "")) if run else None
        if root_node is None and roots:
            root_node = roots[0]
        return {
            "trace_id": trace_id,
            "run": run,
            "root": root_node or {},
            "spans": [nodes[span_id] for span_id in order],
        }

    def get_replay_bundle(self, trace_id: str) -> dict:
        tree = self.get_trace_tree(trace_id)
        spans = [node.get("span", {}) for node in tree.get("spans", [])]
        errors = [
            {
                "span_id": span.get("span_id", ""),
                "name": span.get("name", ""),
                "error_type": span.get("error_type", ""),
                "error_message": span.get("error_message", ""),
            }
            for span in spans
            if span.get("status") == "failed" or span.get("error_message")
        ]
        result_spans = [span for span in spans if span.get("name") == "task.result.received"]
        final_result = result_spans[-1] if result_spans else {}
        output_summary = final_result.get("output_summary") if isinstance(final_result.get("output_summary"), dict) else {}
        artifact_summary = output_summary.get("artifact_summary") or output_summary.get("data_summary") or ""
        return {
            "trace_id": trace_id,
            "run": tree.get("run", {}),
            "span_tree": tree,
            "errors": errors,
            "task": {
                "task_id": tree.get("run", {}).get("task_id", ""),
                "final_status": output_summary.get("status") or tree.get("run", {}).get("status", ""),
                "final_action": output_summary.get("final_action", ""),
                "artifact_summary": artifact_summary,
            },
        }

    def _on_span_start(self, span: TraceSpan) -> None:
        self._append(span.trace_id, {"type": "span_start", "span": asdict(span)})

    def _on_span_end(self, span: TraceSpan) -> None:
        self._append(span.trace_id, {"type": "span_end", "span": asdict(span)})

    def _append(self, trace_id: str, event: dict[str, Any]) -> None:
        try:
            self._store.append_event(trace_id, event)
        except Exception as exc:
            logger.warning(
                f"Trace recorder write failed: trace_id={trace_id}, "
                f"event={event.get('type')}, error={type(exc).__name__}: {exc}"
            )

    def _read_events(self, trace_id: str) -> list[dict[str, Any]]:
        try:
            return self._store.read_events(trace_id)
        except Exception as exc:
            logger.warning(f"Trace recorder read failed: trace_id={trace_id}, error={type(exc).__name__}: {exc}")
            return []

    def _load_run(self, trace_id: str) -> TraceRun | None:
        run_data: dict[str, Any] = {}
        for event in self._read_events(trace_id):
            if event.get("type") in {"run_start", "run_end"} and isinstance(event.get("run"), dict):
                run_data.update(event["run"])
        return TraceRun(**run_data) if run_data else None

    def _load_root_span(self, trace_id: str) -> TraceSpan | None:
        tree = self.get_trace_tree(trace_id)
        span = tree.get("root", {}).get("span")
        return TraceSpan(**span) if isinstance(span, dict) else None


class NullTraceRecorder(TraceRecorder):
    def __init__(self) -> None:
        self._store = InMemoryTraceStore()

    def start_trace(
        self,
        source: str,
        session_id: str = "",
        task_id: str = "",
        audience: str = "",
        attributes: dict | None = None,
    ) -> dict:
        del source, session_id, task_id, audience, attributes
        return {"trace_id": "", "parent_span_id": "", "source": ""}

    def current_trace_context(self) -> dict:
        return {"trace_id": "", "parent_span_id": ""}

    def span(
        self,
        name: str,
        kind: str = "system",
        trace_id: str = "",
        parent_span_id: str = "",
        session_id: str = "",
        task_id: str = "",
        attributes: dict | None = None,
        input_summary: dict | None = None,
    ) -> _NullSpanContext:
        del name, kind, trace_id, parent_span_id, session_id, task_id, attributes, input_summary
        return _NullSpanContext()

    def finish_trace(self, trace_id: str, status: str = "success", error: Any = None) -> None:
        del trace_id, status, error

    def get_trace_tree(self, trace_id: str) -> dict:
        return {"trace_id": trace_id, "run": {}, "root": {}, "spans": []}

    def get_replay_bundle(self, trace_id: str) -> dict:
        return {"trace_id": trace_id, "run": {}, "span_tree": {}, "errors": [], "task": {}}


_recorder: TraceRecorder | NullTraceRecorder | None = None
_recorder_enabled: bool | None = None


def get_trace_recorder() -> TraceRecorder:
    global _recorder, _recorder_enabled
    enabled = _trace_store_enabled()
    if _recorder is None or _recorder_enabled is not enabled:
        _recorder = TraceRecorder(JsonlTraceStore()) if enabled else NullTraceRecorder()
        _recorder_enabled = enabled
    return _recorder


def _trace_store_enabled() -> bool:
    raw = os.environ.get("ENABLE_TRACE_STORE")
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _error_details(error: Any) -> tuple[str, str]:
    if isinstance(error, BaseException):
        return type(error).__name__, str(error)
    if isinstance(error, dict):
        return str(error.get("type") or ""), str(error.get("message") or error)
    return type(error).__name__, str(error)


__all__ = [
    "TraceSpan",
    "TraceRun",
    "TraceRecorder",
    "NullTraceRecorder",
    "JsonlTraceStore",
    "InMemoryTraceStore",
    "current_trace_id",
    "current_span_id",
    "sanitize",
    "get_trace_recorder",
]
