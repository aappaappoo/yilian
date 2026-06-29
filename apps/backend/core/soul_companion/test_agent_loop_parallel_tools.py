import asyncio
import copy
import json

from core.soul_companion import agent_loop


def test_same_turn_tools_run_concurrently_and_preserve_order(monkeypatch):
    tool_calls = [
        {
            "id": "call-weather",
            "function": {
                "name": "weather",
                "arguments": json.dumps({"city": "福州"}, ensure_ascii=False),
            },
        },
        {
            "id": "call-local",
            "function": {
                "name": "local_search",
                "arguments": json.dumps({"place": "福州", "category": "scenic"}, ensure_ascii=False),
            },
        },
    ]
    model_messages = [
        {"content": "", "tool_calls": tool_calls},
        {"content": "查询完成。"},
    ]
    captured_requests = []
    started_tools = []
    both_tools_started = asyncio.Event()

    monkeypatch.setattr(
        agent_loop,
        "_resolve_provider",
        lambda: {
            "provider": "test",
            "model": "test-model",
            "base_url": "https://example.invalid",
            "api_key": "test-key",
        },
    )
    monkeypatch.setattr(agent_loop, "_build_tools", lambda: [])
    monkeypatch.setattr(agent_loop.settings, "soul_agent_tool_concurrency", 10)
    monkeypatch.setattr(agent_loop.settings, "soul_reply_humanizer_enabled", False)

    async def fake_chat_completion(
        _client,
        _cfg,
        messages,
        _tools,
        **_kwargs,
    ):
        captured_requests.append(copy.deepcopy(messages))
        return model_messages.pop(0)

    async def fake_run_tool(
        name,
        arguments,
        *,
        reminder_context,
        location_context,
        progress=None,
    ):
        del reminder_context, location_context, progress
        started_tools.append(name)
        if len(started_tools) == 2:
            both_tools_started.set()
        await asyncio.wait_for(both_tools_started.wait(), timeout=0.2)
        if name == "weather":
            await asyncio.sleep(0.02)
        return json.dumps(
            {"success": True, "text": name, "arguments": dict(arguments)},
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        agent_loop,
        "_chat_completion_with_network_retry",
        fake_chat_completion,
    )
    monkeypatch.setattr(agent_loop, "_run_tool", fake_run_tool)

    result = asyncio.run(
        asyncio.wait_for(
            agent_loop.run_soul_agent("查天气和景点"),
            timeout=1,
        )
    )

    assert started_tools == ["weather", "local_search"]
    assert result.artifact["tools_used"] == ["weather", "local_search"]
    assert [
        item["name"] for item in result.artifact["tool_results"]
    ] == ["weather", "local_search"]
    assert [
        message["name"]
        for message in captured_requests[1]
        if message.get("role") == "tool"
    ] == ["weather", "local_search"]


def test_same_turn_tool_concurrency_limit_is_respected(monkeypatch):
    tool_calls = [
        {
            "id": f"call-{index}",
            "function": {
                "name": "health_query",
                "arguments": json.dumps(
                    {"metric": "blood_pressure", "date": f"2026-06-{22 + index}"},
                    ensure_ascii=False,
                ),
            },
        }
        for index in range(3)
    ]
    model_messages = [
        {"content": "", "tool_calls": tool_calls},
        {"content": "查询完成。"},
    ]
    active_tools = 0
    max_active_tools = 0

    monkeypatch.setattr(
        agent_loop,
        "_resolve_provider",
        lambda: {
            "provider": "test",
            "model": "test-model",
            "base_url": "https://example.invalid",
            "api_key": "test-key",
        },
    )
    monkeypatch.setattr(agent_loop, "_build_tools", lambda: [])
    monkeypatch.setattr(agent_loop.settings, "soul_agent_tool_concurrency", 1)
    monkeypatch.setattr(agent_loop.settings, "soul_reply_humanizer_enabled", False)

    async def fake_chat_completion(
        _client,
        _cfg,
        _messages,
        _tools,
        **_kwargs,
    ):
        return model_messages.pop(0)

    async def fake_run_tool(
        name,
        arguments,
        *,
        reminder_context,
        location_context,
        progress=None,
    ):
        nonlocal active_tools, max_active_tools
        del reminder_context, location_context, progress
        active_tools += 1
        max_active_tools = max(max_active_tools, active_tools)
        await asyncio.sleep(0.01)
        active_tools -= 1
        return json.dumps(
            {"success": True, "text": name, "arguments": dict(arguments)},
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        agent_loop,
        "_chat_completion_with_network_retry",
        fake_chat_completion,
    )
    monkeypatch.setattr(agent_loop, "_run_tool", fake_run_tool)

    result = asyncio.run(agent_loop.run_soul_agent("查最近三天血压"))

    assert max_active_tools == 1
    assert [
        item["name"] for item in result.artifact["tool_results"]
    ] == [
        "health_query",
        "health_query",
        "health_query",
    ]
