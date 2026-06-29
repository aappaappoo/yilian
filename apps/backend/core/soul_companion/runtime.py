"""Soul companion deterministic tool runtime.

This module is the backend-facing adapter for the copied soul-companion tools.
It intentionally keeps the public Soulbot API stable while removing the old
task/agent routing path from text and realtime voice turns.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Sequence

from loguru import logger

from core.config import settings


@dataclass(frozen=True)
class SoulCompanionResult:
    text: str
    source: str
    artifact: Optional[Dict[str, Any]] = None


_PLUGIN_MODULE: Any = None


def _plugin_path() -> Path:
    current = Path(__file__).resolve()
    checked: list[Path] = []

    for parent in current.parents:
        candidate = parent / "plugins" / "soul-companion" / "__init__.py"
        checked.append(candidate)
        if (parent / ".git").exists() and candidate.exists():
            return candidate

    for candidate in checked:
        if candidate.exists():
            return candidate

    raise RuntimeError(
        "Unable to locate soul companion plugin. Checked: "
        + ", ".join(str(path) for path in checked)
    )


def _load_plugin() -> Any:
    global _PLUGIN_MODULE
    if _PLUGIN_MODULE is not None:
        return _PLUGIN_MODULE
    path = _plugin_path()
    spec = importlib.util.spec_from_file_location("soul_companion_plugin", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load soul companion plugin: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _PLUGIN_MODULE = module
    return module


ProgressCallback = Callable[[Dict[str, Any]], Awaitable[None]]
StreamCallback = Callable[[str], Awaitable[None]]


async def _publish_process(
    progress_callback: Optional[ProgressCallback],
    text: str,
) -> None:
    if progress_callback is None:
        return
    try:
        logger.info(f"[soul_companion] 过程：{text}")
        await progress_callback({"type": "assistant_process", "text": text})
    except Exception as exc:
        logger.warning(f"[soul_companion] 过程事件发送失败: {exc}")


async def answer_user_text(
    text: str,
    *,
    recent_messages: Optional[Sequence[Mapping[str, str]]] = None,
    allow_agent: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
    stream_callback: Optional[StreamCallback] = None,
    reminder_context: Optional[Mapping[str, str]] = None,
    default_location_context: Optional[Mapping[str, str]] = None,
) -> SoulCompanionResult:
    """Answer one user turn with the migrated Soul companion tools.

    When the agent loop is enabled, drive the tools with an LLM tool-calling
    loop (full 易联智慧_gpt agent behaviour). This runtime intentionally leaves
    routing to the model and tool schemas, matching the original
    elder-companion project.
    """
    source = str(text or "").strip()
    if not source:
        return SoulCompanionResult(text="你可以再告诉我想查什么。", source="soul_companion:empty")

    del allow_agent

    if settings.soul_agent_enabled:
        try:
            from .agent_loop import SoulAgentNetworkError, run_soul_agent

            await _publish_process(progress_callback, "初始化：读取需求")
            await _publish_process(progress_callback, "判断：准备查询工具")
            return await run_soul_agent(
                source,
                recent_messages=recent_messages,
                progress_callback=progress_callback,
                stream_callback=stream_callback,
                reminder_context=reminder_context,
                default_location_context=default_location_context,
            )
        except SoulAgentNetworkError as exc:
            logger.warning(f"[soul_companion] agent 网络请求失败: {exc}")
            await _publish_process(progress_callback, "网络连接失败")
            return SoulCompanionResult(
                text="我这边连接查询服务的网络一直不稳定，已经重试 5 次还没成功。请稍后再试一次。",
                source="soul_companion:agent_network_unavailable",
                artifact={
                    "tool": "soul_companion_agent",
                    "status": "network_failed",
                    "retry_count": 5,
                },
            )
        except Exception as exc:
            logger.warning(f"[soul_companion] agent 循环失败: {exc}")
            await _publish_process(progress_callback, "审核：查询未完成")

    await _publish_process(progress_callback, "审核：查询未完成")
    return SoulCompanionResult(
        text="我这边暂时没能完成查询，请稍后再试一次。",
        source="soul_companion:agent_unavailable",
        artifact={"tool": "soul_companion_agent", "status": "failed"},
    )
