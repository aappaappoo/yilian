"""Local reminder scheduling for the Soul companion runtime.

The design follows the Hermes cron idea at a smaller scope:
parse a natural-language schedule, persist JSON jobs, tick them with asyncio,
and deliver due reminders back into the active conversation runtime.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from loguru import logger

from core.logging_utils import TOOL_CALL


DeliverReminder = Callable[["ReminderJob"], Awaitable[None]]


@dataclass(frozen=True)
class ParsedReminder:
    message: str
    due_at: datetime
    schedule_text: str
    delay_seconds: float


@dataclass(frozen=True)
class ReminderJob:
    id: str
    session_id: str
    conversation_id: str
    audience: str
    user_id: str
    client_ip: str
    message: str
    due_at: str
    created_at: str
    status: str = "scheduled"
    delivered_at: str = ""
    error: str = ""
    source_text: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ReminderJob":
        return cls(
            id=str(payload.get("id") or ""),
            session_id=str(payload.get("session_id") or ""),
            conversation_id=str(payload.get("conversation_id") or ""),
            audience=str(payload.get("audience") or "Aini"),
            user_id=str(payload.get("user_id") or ""),
            client_ip=str(payload.get("client_ip") or ""),
            message=str(payload.get("message") or ""),
            due_at=str(payload.get("due_at") or ""),
            created_at=str(payload.get("created_at") or ""),
            status=str(payload.get("status") or "scheduled"),
            delivered_at=str(payload.get("delivered_at") or ""),
            error=str(payload.get("error") or ""),
            source_text=str(payload.get("source_text") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "audience": self.audience,
            "user_id": self.user_id,
            "client_ip": self.client_ip,
            "message": self.message,
            "due_at": self.due_at,
            "created_at": self.created_at,
            "status": self.status,
            "delivered_at": self.delivered_at,
            "error": self.error,
            "source_text": self.source_text,
        }

    def with_updates(self, **updates: str) -> "ReminderJob":
        data = self.to_dict()
        data.update(updates)
        return ReminderJob.from_dict(data)


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _format_due_at(due_at: datetime, now: Optional[datetime] = None) -> str:
    base = now or _now()
    if due_at.date() == base.date():
        day = "今天"
    elif due_at.date() == (base + timedelta(days=1)).date():
        day = "明天"
    elif due_at.date() == (base + timedelta(days=2)).date():
        day = "后天"
    else:
        day = due_at.strftime("%Y-%m-%d")
    return f"{day} {due_at:%H:%M}"


def _parse_delay_schedule(schedule: str, now: datetime) -> Optional[tuple[datetime, str]]:
    match = re.fullmatch(
        r"(?P<amount>\d+(?:\.\d+)?)\s*"
        r"(?P<unit>s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)",
        schedule.strip().lower(),
    )
    if not match:
        return None
    amount = float(match.group("amount"))
    if amount <= 0:
        return None
    unit = match.group("unit")
    if unit.startswith("s"):
        seconds = amount
    elif unit.startswith("m"):
        seconds = amount * 60
    elif unit.startswith("h"):
        seconds = amount * 3600
    else:
        seconds = amount * 86400
    due_at = now + timedelta(seconds=seconds)
    return due_at.replace(microsecond=0), match.group(0)


def _parse_iso_schedule(schedule: str) -> Optional[datetime]:
    raw = schedule.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        due_at = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if due_at.tzinfo is not None:
        due_at = due_at.astimezone().replace(tzinfo=None)
    return due_at.replace(microsecond=0)


def parse_structured_reminder(
    *,
    message: str,
    schedule: str,
    now: Optional[datetime] = None,
) -> ParsedReminder:
    """Parse a structured reminder tool call.

    This intentionally does not infer reminder intent from free-form user text.
    The LLM must call the reminder tool and provide a normalized schedule such
    as ``1m``, ``2h`` or an ISO timestamp.
    """
    current = now or _now()
    content = str(message or "").strip()
    schedule_text = str(schedule or "").strip()
    if not content:
        raise ValueError("请提供提醒内容。")
    if not schedule_text:
        raise ValueError("请提供提醒时间，例如 1m、2h 或 2026-06-16T18:30:00。")

    parsed_delay = _parse_delay_schedule(schedule_text, current)
    if parsed_delay is not None:
        due_at, label = parsed_delay
    else:
        due_at = _parse_iso_schedule(schedule_text)
        if due_at is None:
            raise ValueError(
                "提醒时间格式不支持。请使用 1m、2h、1d，或 ISO 时间如 2026-06-16T18:30:00。"
            )
        label = _format_due_at(due_at, current)

    if due_at <= current:
        raise ValueError("这个提醒时间已经过去了，请换一个之后的时间。")

    delay_seconds = max(1.0, (due_at - current).total_seconds())
    return ParsedReminder(
        message=content,
        due_at=due_at,
        schedule_text=label,
        delay_seconds=delay_seconds,
    )


def reminder_ack_text(parsed: ParsedReminder, *, now: Optional[datetime] = None) -> str:
    due_label = _format_due_at(parsed.due_at, now)
    return (
        "好的，我记下了。\n\n"
        f"- **提醒内容**：{parsed.message}\n"
        f"- **提醒时间**：{due_label}\n\n"
        "到点我会在这个对话里提醒你。"
    )


def reminder_due_text(job: ReminderJob) -> str:
    return f"提醒时间到了：{job.message}"


class ReminderScheduler:
    """Persistent asyncio reminder scheduler."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self._storage_path = storage_path or Path(
            os.getenv("SOULMEET_REMINDER_JOBS_PATH", str(Path("data") / "soul_reminders.json"))
        )
        self._jobs: Dict[str, ReminderJob] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._deliver: Optional[DeliverReminder] = None
        self._started = False

    @property
    def storage_path(self) -> Path:
        return self._storage_path

    async def start(self, deliver: DeliverReminder) -> None:
        async with self._lock:
            if self._started:
                self._deliver = deliver
                return
            self._deliver = deliver
            self._load_locked()
            for job in list(self._jobs.values()):
                self._schedule_locked(job)
            self._started = True
            logger.info(
                f"[{TOOL_CALL}] | Task=提醒调度器 | 已启动, jobs={len(self._jobs)}, path={self._storage_path}"
            )

    async def stop(self) -> None:
        async with self._lock:
            for task in self._tasks.values():
                task.cancel()
            self._tasks.clear()
            self._started = False
            logger.info(f"[{TOOL_CALL}] | Task=提醒调度器 | 已停止")

    async def create(
        self,
        *,
        session_id: str,
        conversation_id: str,
        audience: str,
        user_id: str,
        client_ip: str,
        parsed: ParsedReminder,
        source_text: str,
    ) -> ReminderJob:
        now = _now()
        job = ReminderJob(
            id=uuid.uuid4().hex[:12],
            session_id=session_id,
            conversation_id=conversation_id,
            audience=audience,
            user_id=user_id,
            client_ip=client_ip,
            message=parsed.message,
            due_at=parsed.due_at.isoformat(),
            created_at=now.isoformat(),
            source_text=source_text,
        )
        async with self._lock:
            self._jobs[job.id] = job
            self._save_locked()
            self._schedule_locked(job)
        logger.info(
            f"[{TOOL_CALL}] | Task=提醒任务创建 | id={job.id}, session={session_id[:8]}, due_at={job.due_at}, message={job.message}"
        )
        return job

    def _load_locked(self) -> None:
        self._jobs.clear()
        if not self._storage_path.exists():
            return
        try:
            raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"[{TOOL_CALL}] | Task=提醒任务读取 | 失败: {exc}")
            return
        items = raw if isinstance(raw, list) else raw.get("jobs", []) if isinstance(raw, dict) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            job = ReminderJob.from_dict(item)
            if job.id:
                self._jobs[job.id] = job

    def _save_locked(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "jobs": [job.to_dict() for job in self._jobs.values()],
        }
        tmp_path = self._storage_path.with_suffix(self._storage_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._storage_path)

    def _schedule_locked(self, job: ReminderJob) -> None:
        if job.status != "scheduled" or not job.due_at:
            return
        old = self._tasks.pop(job.id, None)
        if old is not None and not old.done():
            old.cancel()
        self._tasks[job.id] = asyncio.create_task(self._run_job(job.id))

    async def _run_job(self, job_id: str) -> None:
        try:
            async with self._lock:
                job = self._jobs.get(job_id)
            if job is None:
                return
            due_at = datetime.fromisoformat(job.due_at)
            await asyncio.sleep(max(0.0, (due_at - _now()).total_seconds()))

            async with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.status != "scheduled":
                    return

            if self._deliver is None:
                raise RuntimeError("Reminder delivery callback is not configured")
            await self._deliver(job)

            async with self._lock:
                current = self._jobs.get(job_id)
                if current is not None:
                    self._jobs[job_id] = current.with_updates(
                        status="delivered",
                        delivered_at=_now().isoformat(),
                        error="",
                    )
                    self._save_locked()
                    self._tasks.pop(job_id, None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"[{TOOL_CALL}] | Task=提醒任务触发 | id={job_id}, 失败: {exc}")
            async with self._lock:
                current = self._jobs.get(job_id)
                if current is not None:
                    self._jobs[job_id] = current.with_updates(
                        status="failed",
                        delivered_at=_now().isoformat(),
                        error=str(exc),
                    )
                    self._save_locked()
                    self._tasks.pop(job_id, None)


reminder_scheduler = ReminderScheduler()
