import asyncio

import httpx
import pytest

from core.soul_companion import agent_loop


class FailingClient:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def post(self, *args, **kwargs):
        del args, kwargs
        self.calls += 1
        raise self.exc


class EventuallySuccessfulClient:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def post(self, *args, **kwargs):
        del args, kwargs
        self.calls += 1
        if self.calls <= self.failures:
            raise httpx.ConnectError("temporary network failure")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "好了"}}]},
            request=httpx.Request("POST", "https://llm.example.test/chat/completions"),
        )


async def _no_sleep(delay: float) -> None:
    del delay


def test_chat_completion_retries_network_errors_five_times(monkeypatch):
    monkeypatch.setattr(agent_loop.asyncio, "sleep", _no_sleep)
    progress_events = []

    async def progress_callback(payload):
        progress_events.append(payload)

    client = FailingClient(httpx.ConnectError("network down"))

    with pytest.raises(agent_loop.SoulAgentNetworkError):
        asyncio.run(agent_loop._chat_completion_with_network_retry(
            client,
            {"model": "test-model", "base_url": "https://llm.example.test/chat/completions", "api_key": "key"},
            [{"role": "user", "content": "hello"}],
            tools=None,
            progress_callback=progress_callback,
            progress_history=[],
            retry_budget=agent_loop.NetworkRetryBudget(),
        ))

    assert client.calls == 6
    assert [event["text"] for event in progress_events] == [
        "网络不稳，重试查询（1/5）",
        "网络不稳，重试查询（2/5）",
        "网络不稳，重试查询（3/5）",
        "网络不稳，重试查询（4/5）",
        "网络不稳，重试查询（5/5）",
    ]


def test_chat_completion_does_not_retry_non_network_status(monkeypatch):
    monkeypatch.setattr(agent_loop.asyncio, "sleep", _no_sleep)
    request = httpx.Request("POST", "https://llm.example.test/chat/completions")
    response = httpx.Response(401, request=request)
    client = FailingClient(httpx.HTTPStatusError("unauthorized", request=request, response=response))
    progress_events = []

    async def progress_callback(payload):
        progress_events.append(payload)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(agent_loop._chat_completion_with_network_retry(
            client,
            {"model": "test-model", "base_url": "https://llm.example.test/chat/completions", "api_key": "key"},
            [{"role": "user", "content": "hello"}],
            tools=None,
            progress_callback=progress_callback,
            progress_history=[],
            retry_budget=agent_loop.NetworkRetryBudget(),
        ))

    assert client.calls == 1
    assert progress_events == []


def test_chat_completion_returns_after_retry_success(monkeypatch):
    monkeypatch.setattr(agent_loop.asyncio, "sleep", _no_sleep)
    progress_events = []

    async def progress_callback(payload):
        progress_events.append(payload)

    client = EventuallySuccessfulClient(failures=2)
    result = asyncio.run(agent_loop._chat_completion_with_network_retry(
        client,
        {"model": "test-model", "base_url": "https://llm.example.test/chat/completions", "api_key": "key"},
        [{"role": "user", "content": "hello"}],
        tools=None,
        progress_callback=progress_callback,
        progress_history=[],
        retry_budget=agent_loop.NetworkRetryBudget(),
    ))

    assert result == {"content": "好了"}
    assert client.calls == 3
    assert [event["text"] for event in progress_events] == [
        "网络不稳，重试查询（1/5）",
        "网络不稳，重试查询（2/5）",
    ]


def test_chat_completion_shares_retry_budget_across_calls(monkeypatch):
    monkeypatch.setattr(agent_loop.asyncio, "sleep", _no_sleep)
    progress_events = []

    async def progress_callback(payload):
        progress_events.append(payload)

    retry_budget = agent_loop.NetworkRetryBudget()
    first_client = EventuallySuccessfulClient(failures=3)
    first_result = asyncio.run(agent_loop._chat_completion_with_network_retry(
        first_client,
        {"model": "test-model", "base_url": "https://llm.example.test/chat/completions", "api_key": "key"},
        [{"role": "user", "content": "hello"}],
        tools=None,
        progress_callback=progress_callback,
        progress_history=[],
        retry_budget=retry_budget,
    ))

    assert first_result == {"content": "好了"}
    assert retry_budget.used == 3

    second_client = FailingClient(httpx.ConnectError("still down"))
    with pytest.raises(agent_loop.SoulAgentNetworkError):
        asyncio.run(agent_loop._chat_completion_with_network_retry(
            second_client,
            {"model": "test-model", "base_url": "https://llm.example.test/chat/completions", "api_key": "key"},
            [{"role": "user", "content": "again"}],
            tools=None,
            progress_callback=progress_callback,
            progress_history=[],
            retry_budget=retry_budget,
        ))

    assert second_client.calls == 3
    assert retry_budget.used == 5
    assert [event["text"] for event in progress_events] == [
        "网络不稳，重试查询（1/5）",
        "网络不稳，重试查询（2/5）",
        "网络不稳，重试查询（3/5）",
        "网络不稳，重试查询（4/5）",
        "网络不稳，重试查询（5/5）",
    ]
