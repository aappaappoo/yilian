import asyncio
import copy
import json

from core.soul_companion import agent_loop
from core.soul_companion import skills as runtime_skills


def _write_skill(path, name="verify-skill"):
    skill_dir = path / name
    skill_dir.mkdir()
    references_dir = skill_dir / "references"
    references_dir.mkdir()
    (references_dir / "guide.md").write_text(
        "# Guide\n\nREFERENCE_CONTENT",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        """---
name: verify-skill
description: 当用户要求 verify-skill 时，用固定校验规则回答。
triggers:
  - verify-skill
requires_tools:
  - weather
---

# Verify Skill

命中本 skill 时，最终回答必须包含 `VERIFY_SKILL_ACTIVE`。
""",
        encoding="utf-8",
    )
    return skill_dir


def test_runtime_skill_install_and_index_prompt(tmp_path, monkeypatch):
    source_dir = _write_skill(tmp_path)
    install_dir = tmp_path / "installed"
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_dir", str(install_dir))
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_enabled", True)

    entry = runtime_skills.install_skill(str(source_dir))

    assert entry["name"] == "verify-skill"
    installed = runtime_skills.list_installed_skills()
    assert [skill.name for skill in installed] == ["verify-skill"]

    prompt = runtime_skills.build_soul_skill_index_prompt(
        available_tools=["skill_view", "weather"],
    )

    assert prompt.active_skills == []
    assert "- verify-skill:" in prompt.prompt
    assert "当用户要求 verify-skill 时" in prompt.prompt
    assert "VERIFY_SKILL_ACTIVE" not in prompt.prompt

    viewed = runtime_skills.view_soul_skill(
        "verify-skill",
        available_tools=["skill_view", "weather"],
    )
    assert viewed["success"] is True
    assert viewed["name"] == "verify-skill"
    assert "VERIFY_SKILL_ACTIVE" in viewed["content"]
    assert viewed["linked_files"] == {"references": ["references/guide.md"]}

    support = runtime_skills.view_soul_skill(
        "verify-skill",
        file_path="references/guide.md",
        available_tools=["skill_view", "weather"],
    )
    assert support["success"] is True
    assert support["file_path"] == "references/guide.md"
    assert "REFERENCE_CONTENT" in support["content"]

    traversal = runtime_skills.view_soul_skill(
        "verify-skill",
        file_path="../guide.md",
        available_tools=["skill_view", "weather"],
    )
    assert traversal["success"] is False
    assert ".." in traversal["error"]


def test_builtin_reply_humanizer_is_final_reply_only(tmp_path, monkeypatch):
    install_dir = tmp_path / "installed"
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_dir", str(install_dir))
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_enabled", True)
    monkeypatch.setattr(runtime_skills.settings, "soul_reply_humanizer_enabled", True)

    entry = runtime_skills.install_skill("builtin/reply-humanizer")

    assert entry["name"] == "reply-humanizer"
    normal_prompt = runtime_skills.build_soul_skill_index_prompt(
        available_tools=["skill_view", "weather"],
    )
    final_prompt = runtime_skills.build_reply_humanizer_prompt()

    assert normal_prompt.active_skills == []
    assert final_prompt.active_skills == ["reply-humanizer"]
    assert "Aini 最终回复表达规范" in final_prompt.prompt


def test_builtin_travel_planner_loads_as_runtime_workflow(tmp_path, monkeypatch):
    install_dir = tmp_path / "installed"
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_dir", str(install_dir))
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_enabled", True)

    entry = runtime_skills.install_skill("builtin/travel-planner")

    assert entry["name"] == "travel-planner"
    prompt = runtime_skills.build_soul_skill_index_prompt(
        available_tools=[
            "skill_view",
            "weather",
            "local_search",
        ],
    )
    assert "- travel-planner:" in prompt.prompt
    assert "soul_travel_plan" not in prompt.prompt

    viewed = runtime_skills.view_soul_skill(
        "travel-planner",
        available_tools=[
            "skill_view",
            "weather",
            "local_search",
        ],
    )
    assert viewed["success"] is True
    assert "不要使用本 skill" in viewed["content"]
    assert viewed["linked_files"]["references"] == [
        "references/dependency-flow.md",
        "references/elder-low-walk.md",
        "references/food-query-templates.md",
        "references/scenic-query-templates.md",
        "references/weather-routing.md",
    ]
    assert "weather" in viewed["content"]
    assert "train_tickets" in viewed["content"]
    assert "train_ticket_price" in viewed["content"]
    assert "local_search" in viewed["content"]

    dependency = runtime_skills.view_soul_skill(
        "travel-planner",
        file_path="references/dependency-flow.md",
        available_tools=["skill_view", "weather", "local_search"],
    )
    assert dependency["success"] is True
    assert "第一批可并行" in dependency["content"]

    missing_core_tool_prompt = runtime_skills.build_soul_skill_index_prompt(
        available_tools=["skill_view", "weather"],
    )
    assert "- travel-planner:" not in missing_core_tool_prompt.prompt


def test_builtin_guide_loads_as_web_reference_skill(tmp_path, monkeypatch):
    install_dir = tmp_path / "installed"
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_dir", str(install_dir))
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_enabled", True)

    entry = runtime_skills.install_skill("builtin/guide")

    assert entry["name"] == "guide"
    prompt = runtime_skills.build_soul_skill_index_prompt(
        available_tools=[
            "skill_view",
            "web_search",
        ],
    )
    assert "- guide:" in prompt.prompt
    assert "泛泛询问旅游攻略" in prompt.prompt

    viewed = runtime_skills.view_soul_skill(
        "guide",
        available_tools=[
            "skill_view",
            "web_search",
        ],
    )
    assert viewed["success"] is True
    assert "不要调用 `weather`" in viewed["content"]
    assert "travel-planner" in viewed["content"]
    assert "web_search" in viewed["content"]

    missing_web_prompt = runtime_skills.build_soul_skill_index_prompt(
        available_tools=["skill_view", "weather", "local_search"],
    )
    assert "- guide:" not in missing_web_prompt.prompt


def test_agent_loop_no_longer_exposes_travel_aggregator():
    tool_names = {name for name, _schema in agent_loop._TOOL_SPECS}
    assert "soul_travel_plan" not in tool_names
    assert all(not name.startswith("soul_") for name in tool_names)
    assert "train_tickets" in tool_names
    assert "train_ticket_price" in tool_names


def test_guide_blocks_web_extract_unless_user_asks_for_page_reading():
    assert agent_loop._is_blocked_tool_call(
        "web_extract",
        loaded_skills=["guide"],
        user_text="厦门怎么玩",
        used_tools=[],
    )
    assert not agent_loop._is_blocked_tool_call(
        "web_extract",
        loaded_skills=["guide"],
        user_text="打开这些网页链接逐个核验一下",
        used_tools=[],
    )
    assert not agent_loop._is_blocked_tool_call(
        "web_extract",
        loaded_skills=["travel-planner"],
        user_text="厦门怎么玩",
        used_tools=[],
    )
    assert not agent_loop._is_blocked_tool_call(
        "web_search",
        loaded_skills=["guide"],
        user_text="厦门怎么玩",
        used_tools=["web_search"],
    )
    assert agent_loop._is_blocked_tool_call(
        "web_search",
        loaded_skills=["guide"],
        user_text="厦门怎么玩",
        used_tools=["web_search", "web_search"],
    )


def test_guide_fast_path_only_matches_generic_guide_queries():
    skill_prompt = "- guide: 中文旅游攻略参考。用于泛泛询问旅游攻略、怎么玩、几日游、自由行。"

    assert agent_loop._is_guide_fast_path_request("厦门怎么玩", skill_prompt=skill_prompt)
    assert agent_loop._is_guide_fast_path_request(
        "想去吴荣木齐玩，玩7天你给我一个旅游gong lüe",
        skill_prompt=skill_prompt,
    )
    assert not agent_loop._is_guide_fast_path_request(
        "帮我做明天福州到厦门一日游，适合老人，少走路",
        skill_prompt=skill_prompt,
    )
    assert not agent_loop._is_guide_fast_path_request("只查天气", skill_prompt=skill_prompt)
    assert not agent_loop._is_guide_fast_path_request(
        "厦门怎么玩",
        skill_prompt="- travel-planner: 旅游规划",
    )


def test_guide_fast_path_builds_rich_strategy_for_guide_requests():
    assert agent_loop._guide_fast_mode("我想去厦门玩帮我做一下攻略") == "rich"
    assert agent_loop._guide_fast_mode("厦门怎么玩") == "short"

    args = agent_loop._guide_fast_search_args(
        "我想去厦门玩帮我做一下攻略",
        mode="rich",
    )
    joined_queries = "\n".join(args["search_queries"])
    assert "厦门 3天4天 旅游攻略 经典路线 景点" in joined_queries
    assert "厦门 必吃美食 小吃 老字号 美食街" in joined_queries
    assert "厦门 住宿区域 交通 预约 注意事项" in joined_queries
    assert args["limit"] == 12

    prompt = agent_loop._guide_fast_system_prompt("", mode="rich")
    assert "核心体验速览" in prompt
    assert "Day 1：主题" in prompt
    assert "地道美食寻味" in prompt
    assert "实用行前贴士" in prompt
    assert "不要因为产品面向老人就默认写老人友好攻略" in prompt
    assert "不要在正文插入引用编号或小圆点" in prompt


def test_agent_loop_uses_guide_fast_path_for_generic_guide(tmp_path, monkeypatch):
    install_dir = tmp_path / "installed"
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_dir", str(install_dir))
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_enabled", True)
    monkeypatch.setattr(runtime_skills.settings, "soul_reply_humanizer_enabled", True)
    runtime_skills.install_skill("builtin/guide")
    runtime_skills.install_skill("builtin/reply-humanizer")

    tool_calls = []
    captured_llm_requests = []
    progress_events = []

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
    monkeypatch.setattr(agent_loop, "_build_tools", lambda: [
        {
            "type": "function",
            "function": {
                "name": "skill_view",
                "description": "skill view",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "web search",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ])

    async def fake_run_tool(name, arguments, **_kwargs):
        tool_calls.append({"name": name, "arguments": dict(arguments)})
        assert name == "web_search"
        assert arguments["limit"] == 12
        assert "乌鲁木齐" in arguments["objective"]
        assert "乌鲁木齐 7天 旅游攻略 经典路线 景点" in arguments["search_queries"]
        assert "乌鲁木齐 必吃美食 小吃 老字号 美食街" in arguments["search_queries"]
        return json.dumps(
            {
                "success": True,
                "text": "搜索结果（来源：parallel）：\n1. 乌鲁木齐攻略 — https://example.com/u",
                "web_search": {
                    "source": "parallel",
                    "results": [
                        {
                            "title": "乌鲁木齐攻略",
                            "url": "https://example.com/u",
                            "description": "经典路线和美食住宿建议",
                        }
                    ],
                },
            },
            ensure_ascii=False,
        )

    async def fake_chat_completion(_client, _cfg, messages, tools, **_kwargs):
        captured_llm_requests.append(copy.deepcopy(messages))
        assert tools is None
        assert any(event.get("type") == "assistant_sources" for event in progress_events)
        assert "guide 泛旅游攻略快链路" in messages[0]["content"]
        assert "Aini 最终回复表达规范" in messages[0]["content"]
        assert "地道美食寻味" in messages[0]["content"]
        assert "联网搜索结果" in messages[-1]["content"]
        return {"content": "乌鲁木齐 7 天可以按市区、天山天池、吐鲁番方向轻松安排。", "tool_calls": []}

    monkeypatch.setattr(agent_loop, "_run_tool", fake_run_tool)
    monkeypatch.setattr(agent_loop, "_chat_completion_with_network_retry", fake_chat_completion)

    async def record_progress(payload):
        progress_events.append(dict(payload))

    result = asyncio.run(agent_loop.run_soul_agent(
        "想去吴荣木齐玩，玩7天你给我一个旅游gong lüe",
        progress_callback=record_progress,
    ))

    assert result.text == "乌鲁木齐 7 天可以按市区、天山天池、吐鲁番方向轻松安排。"
    assert result.artifact["fast_path"] == "guide"
    assert result.artifact["guide_mode"] == "rich"
    assert result.artifact["tools_used"] == ["web_search"]
    assert result.artifact["skills_used"] == ["guide", "reply-humanizer"]
    assert [call["name"] for call in tool_calls] == ["web_search"]
    assert len(captured_llm_requests) == 1
    source_events = [event for event in progress_events if event.get("type") == "assistant_sources"]
    assert source_events[0]["references"] == [
        {"label": "乌鲁木齐攻略", "url": "https://example.com/u"},
    ]


def test_agent_loop_loads_runtime_skill_via_skill_view(tmp_path, monkeypatch):
    source_dir = _write_skill(tmp_path)
    install_dir = tmp_path / "installed"
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_dir", str(install_dir))
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_enabled", True)
    runtime_skills.install_skill(str(source_dir))

    captured_requests = []

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
    monkeypatch.setattr(agent_loop, "_build_tools", lambda: [
        {
            "type": "function",
            "function": {
                "name": "skill_view",
                "description": "skill view",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "weather",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ])

    async def fake_chat_completion(
        _client,
        _cfg,
        messages,
        _tools,
        **_kwargs,
    ):
        captured_requests.append(copy.deepcopy(messages))
        if len(captured_requests) == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_skill",
                        "type": "function",
                        "function": {
                            "name": "skill_view",
                            "arguments": json.dumps({"name": "verify-skill"}),
                        },
                    }
                ],
            }
        tool_messages = [message for message in messages if message.get("role") == "tool"]
        assert tool_messages
        assert "VERIFY_SKILL_ACTIVE" in tool_messages[-1]["content"]
        return {"content": "VERIFY_SKILL_ACTIVE 已生效。", "tool_calls": []}

    monkeypatch.setattr(
        agent_loop,
        "_chat_completion_with_network_retry",
        fake_chat_completion,
    )

    result = asyncio.run(agent_loop.run_soul_agent("请使用 verify-skill 回答"))

    system_message = captured_requests[0][0]["content"]
    assert "工具并行与串行规则" in system_message
    assert "- verify-skill:" in system_message
    assert "VERIFY_SKILL_ACTIVE" not in system_message
    assert result.artifact["skills_used"] == ["verify-skill"]
    assert result.artifact["tools_used"] == []
    skill_result = result.artifact["tool_results"][0]["result"]
    assert skill_result["name"] == "verify-skill"
    assert "content" not in skill_result


def test_agent_loop_applies_reply_humanizer_inline(tmp_path, monkeypatch):
    install_dir = tmp_path / "installed"
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_dir", str(install_dir))
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_enabled", True)
    monkeypatch.setattr(runtime_skills.settings, "soul_reply_humanizer_enabled", True)
    runtime_skills.install_skill("builtin/reply-humanizer")

    captured_requests = []

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

    async def fake_chat_completion(
        _client,
        _cfg,
        messages,
        tools,
        **_kwargs,
    ):
        captured_requests.append(copy.deepcopy(messages))
        assert "Aini 最终回复表达规范" in messages[0]["content"]
        assert tools == []
        return {"content": "今天先好好歇一会儿。觉得舒服了，再慢慢走几步。", "tool_calls": []}

    monkeypatch.setattr(
        agent_loop,
        "_chat_completion_with_network_retry",
        fake_chat_completion,
    )

    result = asyncio.run(agent_loop.run_soul_agent("奶奶今天有点累，安慰她两句"))

    assert result.text == "今天先好好歇一会儿。觉得舒服了，再慢慢走几步。"
    assert result.artifact["skills_used"] == ["reply-humanizer"]
    assert len(captured_requests) == 1


def test_agent_loop_applies_reply_humanizer_inline_for_forced_final_answer(tmp_path, monkeypatch):
    install_dir = tmp_path / "installed"
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_dir", str(install_dir))
    monkeypatch.setattr(runtime_skills.settings, "soul_skills_enabled", True)
    monkeypatch.setattr(runtime_skills.settings, "soul_reply_humanizer_enabled", True)
    monkeypatch.setattr(agent_loop.settings, "soul_agent_max_turns", 1)
    runtime_skills.install_skill("builtin/reply-humanizer")

    captured = []

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
    monkeypatch.setattr(agent_loop, "_build_tools", lambda: [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "weather",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ])

    async def fake_run_tool(*_args, **_kwargs):
        return json.dumps({"ok": True, "summary": "今天适合休息"}, ensure_ascii=False)

    async def fake_chat_completion(_client, _cfg, messages, tools, **_kwargs):
        captured.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)})
        assert "Aini 最终回复表达规范" in messages[0]["content"]
        if len(captured) == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "weather", "arguments": "{}"},
                    }
                ],
            }
        if len(captured) == 2:
            assert tools is None
            assert messages[-1]["content"] == "请根据以上已查询到的结果，直接给出最终中文答复，不要再调用工具。"
            return {"content": "今天就安心歇一歇，别急着出门。", "tool_calls": []}
        raise AssertionError("reply-humanizer must not trigger a second LLM call")

    monkeypatch.setattr(agent_loop, "_run_tool", fake_run_tool)
    monkeypatch.setattr(agent_loop, "_chat_completion_with_network_retry", fake_chat_completion)

    result = asyncio.run(agent_loop.run_soul_agent("今天适合出门吗"))

    assert result.text == "今天就安心歇一歇，别急着出门。"
    assert result.artifact["skills_used"] == ["reply-humanizer"]
    assert result.artifact["tools_used"] == ["weather"]
    assert len(captured) == 2
