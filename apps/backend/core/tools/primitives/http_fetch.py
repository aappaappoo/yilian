"""
HTTP 原语

纯 HTTP GET/POST，无业务文案。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger
from core.logging_utils import TOOL_CALL


class HttpFetchError(Exception):
    """HTTP 请求失败异常。"""

    def __init__(self, message: str, url: str = "", status: int = 0) -> None:
        self.url = url
        self.status = status
        super().__init__(message)


class HttpFetch:
    """HTTP 原语：纯 HTTP 请求，不含 API URL、不含自然语言文案。"""

    def __init__(self, default_timeout: float = 10.0) -> None:
        self._default_timeout = default_timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """确保存在可复用的 aiohttp session。"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """关闭底层 HTTP session。"""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def fetch(
        self,
        url: str,
        params: Optional[Dict[str, str]] = None,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        执行 HTTP 请求。

        Args:
            url:       请求地址
            params:    URL 查询参数
            method:    HTTP 方法 ("GET" / "POST")
            headers:   请求头
            json_body: POST JSON body
            timeout:   超时秒数（None 使用 default_timeout）

        Returns:
            Dict[str, Any]: 响应 JSON 解析结果

        Raises:
            HttpFetchError: 请求失败或超时
        """
        try:
            session = await self._ensure_session()
            actual_timeout = timeout if timeout is not None else self._default_timeout
            client_timeout = aiohttp.ClientTimeout(total=actual_timeout)
            kwargs: Dict[str, Any] = {"timeout": client_timeout}
            if params:
                kwargs["params"] = params
            if headers:
                kwargs["headers"] = headers
            if json_body and method.upper() == "POST":
                kwargs["json"] = json_body

            logger.debug(f"[{TOOL_CALL}] | Task=HTTP请求 | HTTP {method} {url} → sending request")
            async with session.request(method.upper(), url, **kwargs) as resp:
                logger.debug(f"[{TOOL_CALL}] | Task=HTTP请求 | HTTP {method} {url} → status={resp.status}")
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientResponseError as e:
            logger.debug(
                f"[{TOOL_CALL}] | Task=HTTP请求 | HTTP {method} {url} → ClientResponseError: status={e.status}, message={e.message}"
            )
            raise HttpFetchError(
                f"HTTP {method} {url} failed: {e}", url=url, status=e.status
            ) from e
        except Exception as e:
            logger.debug(f"[{TOOL_CALL}] | Task=HTTP请求 | HTTP {method} {url} → {type(e).__name__}: {e}")
            raise HttpFetchError(
                f"HTTP {method} {url} failed: {e}", url=url
            ) from e

    async def fetch_with_retry(
        self,
        url: str,
        params=None,
        method: str = "GET",
        headers=None,
        json_body=None,
        timeout: Optional[float] = None,
        retry_count: int = 3,
        retry_backoff_max: float = 8.0,
        on_retry=None,
    ) -> Dict[str, Any]:
        """带重试+指数退避的 HTTP 请求。

        retry_count: 最大重试次数（不含首次）
        retry_backoff_max: 退避上限（秒）
        on_retry: 可选的异步回调 async (attempt: int, exc: Exception) -> None，
                  在每次重试前调用，attempt 从 1 开始计数。
        """
        for attempt in range(1 + retry_count):
            try:
                return await self.fetch(
                    url,
                    params=params,
                    method=method,
                    headers=headers,
                    json_body=json_body,
                    timeout=timeout,
                )
            except Exception as exc:
                if attempt < retry_count:
                    wait = min(2 ** attempt, retry_backoff_max)
                    logger.warning(
                        f"[{TOOL_CALL}] | Task=HTTP请求 | HTTP {method} {url} → 失败({type(exc).__name__})，"
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
                        f"[{TOOL_CALL}] | Task=HTTP请求 | HTTP {method} {url} → 失败({type(exc).__name__})，已达最大重试次数 {retry_count}"
                    )
                    raise
