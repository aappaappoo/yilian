"""
定时器原语

创建/取消/列表，无文案。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List
from loguru import logger

from core.logging_utils import TOOL_CALL


class TimerManager:
    """定时器原语：创建/取消/列表，不含业务文案。"""

    def __init__(self) -> None:
        self._timers: Dict[str, asyncio.Task] = {}

    async def _timer_task(
        self,
        name: str,
        seconds: float,
        callback: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        """内部定时器协程。"""
        await asyncio.sleep(seconds)
        await callback()
        self._timers.pop(name, None)

    async def set_timer(
        self,
        name: str,
        seconds: float,
        callback: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        """
        设置定时器。

        Args:
            name:     定时器名称
            seconds:  延迟秒数
            callback: 到期回调（async 无参函数）

        Raises:
            ValueError: seconds <= 0
        """
        if seconds <= 0:
            raise ValueError(f"seconds must be > 0, got {seconds}")

        # 如果已存在同名定时器，先取消
        if name in self._timers and not self._timers[name].done():
            self._timers[name].cancel()

        self._timers[name] = asyncio.create_task(
            self._timer_task(name, seconds, callback)
        )
        logger.info(f"[{TOOL_CALL}] | Task=定时器管理 | set_timer: name='{name}', seconds={seconds:.1f}, is_active=True")

    async def cancel_timer(self, name: str) -> bool:
        """
        取消定时器。

        Returns:
            bool: 是否成功取消（不存在返回 False）
        """
        task = self._timers.pop(name, None)
        if task is not None and not task.done():
            task.cancel()
            logger.info(f"[{TOOL_CALL}] | Task=定时器管理 | cancel_timer: name='{name}', 取消成功")
            return True
        return False

    def list_timers(self, prefix: str = "") -> List[str]:
        """列出所有活跃定时器名称，可按前缀过滤。"""
        return [
            name
            for name, task in self._timers.items()
            if not task.done() and name.startswith(prefix)
        ]

    def is_active(self, name: str) -> bool:
        """检查定时器是否活跃。"""
        task = self._timers.get(name)
        return task is not None and not task.done()

    async def cancel_all(self, prefix: str = "") -> int:
        """取消所有匹配前缀的定时器，返回取消数量。"""
        cancelled = 0
        names = [
            name
            for name, task in self._timers.items()
            if not task.done() and name.startswith(prefix)
        ]
        for name in names:
            task = self._timers.pop(name, None)
            if task is not None and not task.done():
                task.cancel()
                cancelled += 1
        logger.info(f"[{TOOL_CALL}] | Task=定时器管理 | cancel_all: prefix='{prefix}', 取消数={cancelled}")
        return cancelled
