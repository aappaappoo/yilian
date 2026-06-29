"""
Shell 命令执行原语

纯命令行执行，无业务 URL、无自然语言文案。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger
from core.logging_utils import TOOL_CALL


class ShellExecError(Exception):
    """命令行执行失败异常。"""

    def __init__(self, message: str, cmd: str = "", returncode: int = 0) -> None:
        self.cmd = cmd
        self.returncode = returncode
        super().__init__(message)


class ShellExec:
    """Shell 原语：纯命令行执行，不含业务 URL、不含自然语言文案。"""

    def __init__(self, default_timeout: float = 10.0) -> None:
        self._default_timeout = default_timeout

    async def run(
        self,
        args: Sequence[str],
        timeout: Optional[float] = None,
    ) -> str:
        """
        异步执行命令并返回 stdout 字符串。

        Args:
            args:    命令及参数列表，例如 ["curl", "-s", "https://example.com"]
            timeout: 超时秒数（None 使用 default_timeout）

        Returns:
            str: 命令的 stdout 输出

        Raises:
            ShellExecError: 命令执行失败、超时或返回非零退出码
        """
        actual_timeout = timeout if timeout is not None else self._default_timeout
        cmd_str = " ".join(str(a) for a in args)

        logger.debug(f"[{TOOL_CALL}] | Task=Shell命令执行 | Shell cmd='{cmd_str}' → 开始执行")
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=actual_timeout
                )
            except asyncio.TimeoutError as e:
                proc.kill()
                await proc.communicate()
                logger.debug(f"[{TOOL_CALL}] | Task=Shell命令执行 | Shell cmd='{cmd_str}' → TimeoutError after {actual_timeout}s")
                raise ShellExecError(
                    f"Shell cmd '{cmd_str}' timed out after {actual_timeout}s",
                    cmd=cmd_str,
                ) from e

            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")
            returncode = proc.returncode if proc.returncode is not None else -1

            logger.debug(f"[{TOOL_CALL}] | Task=Shell命令执行 | Shell cmd='{cmd_str}' → returncode={returncode}")
            if returncode != 0:
                raise ShellExecError(
                    f"Shell cmd '{cmd_str}' failed: returncode={returncode}, stderr={stderr!r}",
                    cmd=cmd_str,
                    returncode=returncode,
                )
            return stdout
        except ShellExecError:
            raise
        except Exception as e:
            logger.debug(f"[{TOOL_CALL}] | Task=Shell命令执行 | Shell cmd='{cmd_str}' → {type(e).__name__}: {e}")
            raise ShellExecError(
                f"Shell cmd '{cmd_str}' failed: {e}", cmd=cmd_str
            ) from e

    async def run_with_retry(
        self,
        args: Sequence[str],
        timeout: Optional[float] = None,
        retry_count: int = 3,
        retry_backoff_max: float = 8.0,
        on_retry=None,
    ) -> str:
        """带重试+指数退避的命令执行。

        Args:
            args:              命令及参数列表
            timeout:           超时秒数（None 使用 default_timeout）
            retry_count:       最大重试次数（不含首次）
            retry_backoff_max: 退避上限（秒）
            on_retry:          可选的异步回调 async (attempt: int, exc: Exception) -> None，
                               在每次重试前调用，attempt 从 1 开始计数。

        Returns:
            str: 命令的 stdout 输出

        Raises:
            ShellExecError: 所有重试均失败
        """
        cmd_str = " ".join(str(a) for a in args)
        for attempt in range(1 + retry_count):
            try:
                return await self.run(args, timeout=timeout)
            except Exception as exc:
                if attempt < retry_count:
                    wait = min(2 ** attempt, retry_backoff_max)
                    logger.warning(
                        f"[{TOOL_CALL}] | Task=Shell命令执行 | Shell cmd='{cmd_str}' → 失败({type(exc).__name__})，"
                        f"准备重试 ({attempt + 1}/{retry_count})，等待 {wait:.0f}s"
                    )
                    if on_retry is not None:
                        try:
                            await on_retry(attempt + 1, exc)
                        except Exception:
                            pass
                    await asyncio.sleep(wait)
                else:
                    logger.warning(
                        f"[{TOOL_CALL}] | Task=Shell命令执行 | Shell cmd='{cmd_str}' → 失败({type(exc).__name__})，已达最大重试次数 {retry_count}"
                    )
                    raise

    async def curl_json(
        self,
        url: str,
        timeout: Optional[float] = None,
        retry_count: int = 3,
        retry_backoff_max: float = 8.0,
        on_retry=None,
    ) -> Dict[str, Any]:
        """
        使用 curl 请求 URL 并解析 JSON 响应。

        等效于：curl -s -f --max-time <timeout> <url>

        Args:
            url:               请求地址
            timeout:           超时秒数（None 使用 default_timeout）
            retry_count:       最大重试次数（不含首次）
            retry_backoff_max: 退避上限（秒）
            on_retry:          可选的异步回调 async (attempt: int, exc: Exception) -> None，
                               在每次重试前调用，attempt 从 1 开始计数。

        Returns:
            Dict[str, Any]: 响应 JSON 解析结果

        Raises:
            ShellExecError: curl 执行失败或超时
            ValueError:     响应内容无法解析为 JSON
        """
        actual_timeout = timeout if timeout is not None else self._default_timeout
        # Validate URL has a scheme to avoid passing arbitrary strings to curl
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"curl_json: URL must start with http:// or https://, got: {url!r}")
        args: List[str] = [
            "curl",
            "-s",
            "-f",
            "--max-time",
            str(actual_timeout),
            url,
        ]
        # Give asyncio a small buffer over curl's --max-time so curl can exit
        # gracefully before asyncio forcefully kills the process.
        asyncio_timeout = actual_timeout + 5.0
        stdout = await self.run_with_retry(
            args,
            timeout=asyncio_timeout,
            retry_count=retry_count,
            retry_backoff_max=retry_backoff_max,
            on_retry=on_retry,
        )
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as e:
            logger.debug(f"[{TOOL_CALL}] | Task=Shell命令执行 | curl_json url='{url}' → JSON 解析失败: {e}")
            raise ValueError(
                f"curl_json url='{url}' response is not valid JSON: {e}"
            ) from e
