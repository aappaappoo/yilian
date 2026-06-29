"""Soul companion LLM tool-calling agent loop.

This mirrors the 易联智慧_gpt (Hermes) elder-companion agent behaviour: an LLM
decides which soul_* tools to call, chains them across turns, and synthesises a
final Chinese answer.

The HTTP call style matches the rest of the backend (httpx against an
OpenAI-compatible ``/chat/completions`` endpoint), so no extra ``openai``
dependency is introduced. Provider/model/key are configurable via settings; the
default provider is DeepSeek.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence

import httpx
from loguru import logger

from core.config import settings
from core.llm_trace import record_llm_request, record_llm_response

from .default_location import default_location_service
from .reminders import parse_structured_reminder, reminder_ack_text, reminder_scheduler
from .runtime import SoulCompanionResult, _load_plugin
from .skills import (
    build_reply_humanizer_prompt,
    build_soul_skill_index_prompt,
    view_soul_skill,
)


_PROMPT_PATH = Path(__file__).resolve().parent / "prompt.md"
_PROMPT_TEXT: Optional[str] = None
_NETWORK_RETRY_LIMIT = 5
_NETWORK_RETRY_DELAYS = (0.5, 1.0, 2.0, 3.0, 5.0)
_PARALLEL_TOOL_CALL_GUIDANCE = (
    "## 工具并行与串行规则\n"
    "需要查询多项互不依赖的信息时，必须在同一轮一次性发出多个 tool call，不要一项一项等待。"
    "例如天气、去程车次、返程车次、不同日期健康记录、多个公开资料搜索，在参数已明确且互不依赖时应同轮调用。\n"
    "如果后一步必须依赖前一步结果，必须串行等待。例如旅游规划中：景点依赖天气结果，美食依赖已选景点或活动区域；"
    "这类工具不要提前泛查。\n"
    "工具已有结果足够支撑答复时，优先筛选和取舍，不要为了更完美反复补查。"
)
_GUIDE_WEB_EXTRACT_ALLOWED_RE = re.compile(
    r"(打开|读取|查看|核验|验证|逐个|逐页|逐链接|原文|正文|网页|链接|url|URL)"
)
_GUIDE_FAST_TRIGGER_RE = re.compile(
    r"(怎么玩|咋玩|攻略|gong\s*l[üu]e|自由行|旅游路线|旅行路线|"
    r"玩\s*[0-9一二三四五六七八九十两]+\s*(?:天|日))",
    re.IGNORECASE,
)
_GUIDE_RICH_TRIGGER_RE = re.compile(
    r"(攻略|gong\s*l[üu]e|旅游规划|旅行规划|行程|路线|自由行|几日游|"
    r"帮我.*(?:做|写|安排|规划)|做一下|第一次去|"
    r"[0-9一二三四五六七八九十两]+\s*(?:天|日))",
    re.IGNORECASE,
)
_GUIDE_FAST_BLOCK_RE = re.compile(
    r"(今天|明天|后天|大后天|实时|现在|当前|天气|下雨|气温|温度|"
    r"车票|动车|高铁|火车|余票|票价|机票|航班|多少钱|"
    r"附近|营业时间|开放时间|排队|老人|父母|长辈|少走路|不想走太多路|轻松不累|"
    r"查车票|查天气|从\S{1,20}到\S{1,20})"
)
_GUIDE_DESTINATION_PATTERNS = (
    re.compile(r"去(?P<dest>[\u4e00-\u9fffA-Za-z]{2,12}?)(?:玩|旅游|旅行|自由行|攻略)"),
    re.compile(r"(?P<dest>[\u4e00-\u9fffA-Za-z]{2,12}?)(?:怎么玩|咋玩)"),
    re.compile(
        r"(?P<dest>[\u4e00-\u9fffA-Za-z]{2,12}?)\s*"
        r"(?:[0-9一二三四五六七八九十两]+\s*(?:天|日))?\s*"
        r"(?:旅游|旅行|自由行)?\s*(?:攻略|gong\s*l[üu]e)",
        re.IGNORECASE,
    ),
)
_GUIDE_DESTINATION_ALIASES = {
    "吴荣木齐": "乌鲁木齐",
    "乌市": "乌鲁木齐",
}
_GUIDE_INVALID_DESTINATIONS = {
    "一个",
    "旅游",
    "旅行",
    "攻略",
    "自由行",
}

# (tool name, schema attribute on the plugin module). skill_view is first so
# the model can load relevant runtime instructions before business tools.
_TOOL_SPECS: tuple[tuple[str, Optional[str]], ...] = (
    ("skill_view", None),
    ("reminder", None),
    ("set_default_location", None),
    ("weather", "SOUL_WEATHER_SCHEMA"),
    ("train_tickets", "TRAIN_TICKETS_SCHEMA"),
    ("train_ticket_price", "TRAIN_TICKET_PRICE_SCHEMA"),
    ("local_search", "SOUL_LOCAL_SEARCH_SCHEMA"),
    ("health_query", "SOUL_HEALTH_SCHEMA"),
    ("web_search", "WEB_SEARCH_SCHEMA"),
    ("web_extract", "WEB_EXTRACT_SCHEMA"),
)

_LOCAL_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "skill_view": {
        "description": (
            "加载一个 Soulbot runtime skill 的完整说明。skill 是任务流程、领域规则和操作说明，"
            "不是最终答案，也不会执行用户任务。若 system prompt 的 skill 索引中某个 skill 与当前任务相关，"
            "先调用本工具读取 SKILL.md；如返回 linked_files，可按需继续读取 references 等支持文件。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "要加载的 skill 名称，例如 travel-planner。",
                },
                "file_path": {
                    "type": "string",
                    "description": "可选。读取该 skill 目录下的支持文件，例如 references/dependency-flow.md。",
                },
            },
            "required": ["name"],
        },
    },
    "reminder": {
        "description": (
            "设置一次性定时提醒。用户要求稍后、几分钟后、明天某时、到点提醒、叫我、告诉我某事时使用。"
            "不要直接回答没有提醒功能。schedule 必须由模型归一化为 1m、2h、1d 或 ISO 时间。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "到点后要提醒用户的简短内容，例如：需要吃药了。",
                },
                "schedule": {
                    "type": "string",
                    "description": (
                        "提醒时间。相对时间使用 1m、2h、1d 这类格式；绝对时间使用 ISO 格式，"
                        "例如 2026-06-16T18:30:00。"
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "可选，提醒任务名称。",
                },
            },
            "required": ["message", "schedule"],
        },
    },
    "set_default_location": {
        "description": (
            "记录用户明确确认的默认地点。用户说“我在厦门”“以后按泉州查”“默认地点设为莆田”"
            "或在系统要求确认地点后直接给出城市时使用。不要用它记录旅游目的地。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "用户确认作为默认查询地点的城市或区县。"},
                "province": {"type": "string", "description": "可选，省份。"},
            },
            "required": ["city"],
        },
    },
}

ProgressCallback = Callable[[Dict[str, Any]], Awaitable[None]]
StreamCallback = Callable[[str], Awaitable[None]]
ReminderContext = Mapping[str, str]
DefaultLocationContext = Mapping[str, str]


class SoulAgentNetworkError(RuntimeError):
    """Raised after retryable network failures exhaust the agent retry budget."""


@dataclass
class NetworkRetryBudget:
    used: int = 0
    limit: int = _NETWORK_RETRY_LIMIT


def _prompt_text() -> str:
    global _PROMPT_TEXT
    if _PROMPT_TEXT is None:
        _PROMPT_TEXT = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    return _PROMPT_TEXT


def _location_prompt(location_context: Optional[DefaultLocationContext]) -> str:
    if not location_context:
        return (
            "默认地点：未知。用户没有说明城市时，先询问所在城市，不要自行假设城市。"
        )

    city = str(location_context.get("city") or "").strip()
    source = str(location_context.get("source") or "").strip()
    status = str(location_context.get("status") or "").strip()
    reason = str(location_context.get("reason") or "").strip()
    confirmed = str(location_context.get("confirmed") or "").strip().lower() == "true"

    if city and status in {"resolved", "confirmed"}:
        if confirmed:
            return f"默认地点：{city}，来源：用户确认。用户未指定城市时，按这个地点查询。"
        return (
            f"默认地点：{city}，来源：{source or 'IP定位'}。"
            "用户未指定城市时，可以按这个地点查询，并在最终回复中简短说明按该地点处理。"
        )

    reason_text = f"原因：{reason}。" if reason else ""
    return (
        f"默认地点：未确认。{reason_text}"
        "用户没有说明城市时，必须先询问所在城市；用户确认后调用 set_default_location 记录。"
    )


def _system_prompt(
    location_context: Optional[DefaultLocationContext] = None,
    *,
    skill_prompt: str = "",
    final_reply_prompt: str = "",
) -> str:
    today = datetime.now().strftime("%Y-%m-%d %A")
    prompt = (
        f"{_prompt_text()}\n\n"
        f"{_PARALLEL_TOOL_CALL_GUIDANCE}\n\n"
        f"当前日期：{today}。用户未指定日期时，车票/攻略默认按“明天”，天气默认未来 4 天。\n"
        f"{_location_prompt(location_context)}"
    )
    if skill_prompt:
        prompt = f"{prompt}\n\n{skill_prompt}"
    if final_reply_prompt:
        prompt = f"{prompt}\n\n{final_reply_prompt}"
    return prompt


def _resolve_provider() -> Dict[str, str]:
    """Resolve provider/model/base_url/api_key. Default provider is DeepSeek."""
    provider = (settings.soul_agent_provider or "deepseek").lower()
    if provider == "dashscope":
        return {
            "provider": "dashscope",
            "api_key": settings.soul_agent_api_key or settings.dashscope_api_key or "",
            "base_url": (
                settings.soul_agent_base_url
                or "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
            ),
            "model": settings.soul_agent_model or "qwen-plus",
        }
    return {
        "provider": "deepseek",
        "api_key": settings.soul_agent_api_key or settings.deepseek_api_key or "",
        "base_url": settings.soul_agent_base_url or "https://api.deepseek.com/chat/completions",
        "model": settings.soul_agent_model or "deepseek-chat",
    }


def _build_tools() -> List[Dict[str, Any]]:
    plugin = _load_plugin()
    tools: List[Dict[str, Any]] = []
    for name, schema_attr in _TOOL_SPECS:
        if name == "skill_view" and not settings.soul_skills_enabled:
            continue
        schema = _LOCAL_TOOL_SCHEMAS.get(name)
        if schema is None and schema_attr:
            schema = getattr(plugin, schema_attr, None)
        if not isinstance(schema, Mapping):
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema.get("description", ""),
                    "parameters": schema.get(
                        "parameters", {"type": "object", "properties": {}}
                    ),
                },
            }
        )
    return tools


def _tool_schema_description(name: str) -> str:
    local_schema = _LOCAL_TOOL_SCHEMAS.get(name)
    if local_schema is not None:
        return str(local_schema.get("description") or "").strip()
    plugin = _load_plugin()
    schema_attr = next((attr for tool_name, attr in _TOOL_SPECS if tool_name == name), "")
    schema = getattr(plugin, schema_attr, None) if schema_attr else None
    if isinstance(schema, Mapping):
        return str(schema.get("description") or "").strip()
    return ""


def _short_text(value: Any, limit: int = 120) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[:limit].rstrip()}..."


def _argument_summary(arguments: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key, value in arguments.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False)
        else:
            value_text = str(value)
        parts.append(f"{key}={_short_text(value_text, 48)}")
        if len(parts) >= 6:
            break
    return "；".join(parts)


def _progress_value(arguments: Mapping[str, Any], *keys: str, limit: int = 14) -> str:
    for key in keys:
        value = arguments.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
        text = re.sub(r"[\"'{}\\[\\]]", "", text).strip()
        text = " ".join(text.split())
        if text:
            return text[:limit]
    return ""


def _tool_label(name: str) -> str:
    labels = {
        "skill_view": "技能",
        "weather": "天气",
        "train_tickets": "车次",
        "train_ticket_price": "票价",
        "local_search": "地点",
        "health_query": "健康记录",
        "reminder": "提醒",
        "set_default_location": "默认地点",
        "web_search": "联网搜索",
        "web_extract": "网页内容",
    }
    return labels.get(name, "信息")


def _category_label(category: str) -> str:
    labels = {
        "food": "美食",
        "hotel": "住宿",
        "scenic": "景点",
    }
    return labels.get(category, "地点")


def _tool_start_label(name: str, arguments: Mapping[str, Any]) -> str:
    if name == "skill_view":
        skill_name = _progress_value(arguments, "name", limit=24) or "skill"
        return f"加载：{skill_name} skill"

    if name == "weather":
        city = _progress_value(arguments, "city", "place") or "当地"
        return f"查看：{city}天气"

    if name == "reminder":
        return "设置：创建提醒"

    if name == "set_default_location":
        city = _progress_value(arguments, "city", "place") or "默认地点"
        return f"设置：默认地点{city}"

    if name == "train_tickets":
        departure = _progress_value(arguments, "departure", "from", "from_city") or "出发地"
        destination = _progress_value(arguments, "destination", "to", "to_city") or "目的地"
        return f"查询：{departure}到{destination}车次"

    if name == "train_ticket_price":
        train_number = _progress_value(arguments, "train_number", "train_no", "train", limit=12)
        return f"查询：{train_number or '车次'}票价"

    if name == "local_search":
        place = _progress_value(arguments, "place", "city") or "附近"
        keyword = _progress_value(arguments, "keyword", "food_keyword", "hotel_keyword")
        category = _category_label(_progress_value(arguments, "category", limit=12))
        return f"查看：{place}{keyword or category}"

    if name == "health_query":
        labels = {
            "heart_rate": "心率",
            "blood_pressure": "血压",
            "blood_oxygen": "血氧",
            "temperature": "体温",
        }
        metric = _progress_value(arguments, "metric", limit=20)
        date = _progress_value(arguments, "date", "dayTime", limit=12)
        return f"查看：{date or '最近'}{labels.get(metric, '健康记录')}"

    if name == "web_search":
        query = _progress_value(arguments, "query", "q", limit=18) or "资料"
        return f"联网：搜索{query}"

    if name == "web_extract":
        return "联网：读取网页"

    return "查看：相关信息"


def _tool_complete_label(name: str, success: bool) -> str:
    label = _tool_label(name)
    return f"整理：{label}结果" if success else f"审核：{label}失败"


def _tool_result_summary(result: str) -> tuple[bool, str]:
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return True, _short_text(result)

    if not isinstance(payload, Mapping):
        return True, _short_text(payload)

    success = bool(payload.get("success", True))
    summary = (
        payload.get("summary")
        or payload.get("text")
        or payload.get("error")
        or payload.get("message")
        or ""
    )
    return success, _short_text(summary)

async def _emit_agent_progress(
    progress_callback: Optional[ProgressCallback],
    *,
    history: List[Dict[str, Any]],
    phase_label: str,
    description: str = "",
    status: str = "running",
    progress: int = 0,
    phase_key: str = "",
) -> None:
    if progress_callback is None:
        return

    del history, description, status, progress, phase_key
    payload = {"type": "assistant_process", "text": phase_label}
    try:
        logger.info(f"[soul_agent] 过程：{phase_label}")
        await progress_callback(payload)
    except Exception as exc:
        logger.warning(f"[soul_agent] 过程事件发送失败: {exc}")


def _run_plugin_tool_sync(
    name: str,
    arguments: Mapping[str, Any],
    progress: Optional[Callable[[str], None]] = None,
) -> str:
    """Execute one soul_* tool and return its raw JSON string for the model."""
    plugin = _load_plugin()
    fn = getattr(plugin, name, None)
    if fn is None or not callable(fn):
        return json.dumps({"success": False, "error": f"未知工具：{name}"}, ensure_ascii=False)
    try:
        result = str(fn(dict(arguments), progress=progress))
        try:
            payload = json.loads(result)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, Mapping) and not payload.get("success"):
            logger.warning(f"[soul_agent] 工具 {name} 返回失败: {payload.get('error') or '<empty>'}")
        return result
    except Exception as exc:  # tool stays internal; report failure to the model
        logger.warning(f"[soul_agent] 工具 {name} 执行失败: {exc}")
        return json.dumps(
            {"success": False, "error": f"工具执行失败：{exc}"}, ensure_ascii=False
        )


async def _run_reminder_tool(
    arguments: Mapping[str, Any],
    reminder_context: Optional[ReminderContext],
) -> str:
    if reminder_context is None:
        return json.dumps({"success": False, "error": "当前会话不能创建提醒。"}, ensure_ascii=False)
    try:
        parsed = parse_structured_reminder(
            message=str(arguments.get("message") or ""),
            schedule=str(arguments.get("schedule") or ""),
        )
        job = await reminder_scheduler.create(
            session_id=str(reminder_context.get("session_id") or ""),
            conversation_id=str(reminder_context.get("conversation_id") or ""),
            audience=str(reminder_context.get("audience") or "Aini"),
            user_id=str(reminder_context.get("user_id") or ""),
            client_ip=str(reminder_context.get("client_ip") or ""),
            parsed=parsed,
            source_text=str(reminder_context.get("source_text") or ""),
        )
        return json.dumps(
            {
                "success": True,
                "text": reminder_ack_text(parsed),
                "summary": f"{parsed.schedule_text}提醒：{parsed.message}",
                "reminder": job.to_dict(),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.warning(f"[soul_agent] 提醒工具执行失败: {exc}")
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


async def _run_default_location_tool(
    arguments: Mapping[str, Any],
    location_context: Optional[DefaultLocationContext],
) -> str:
    if location_context is None:
        return json.dumps({"success": False, "error": "当前会话不能记录默认地点。"}, ensure_ascii=False)
    try:
        location = default_location_service.confirm(
            city=str(arguments.get("city") or ""),
            province=str(arguments.get("province") or ""),
            session_id=str(location_context.get("session_id") or ""),
            user_id=str(location_context.get("user_id") or ""),
            client_ip=str(location_context.get("client_ip") or ""),
        )
        return json.dumps(
            {
                "success": True,
                "text": f"已把{location.city}设为默认查询地点。",
                "summary": f"默认地点：{location.city}",
                "default_location": location.to_prompt_context(),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.warning(f"[soul_agent] 默认地点工具执行失败: {exc}")
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


async def _run_tool(
    name: str,
    arguments: Mapping[str, Any],
    *,
    reminder_context: Optional[ReminderContext],
    location_context: Optional[DefaultLocationContext],
    progress: Optional[Callable[[str], None]] = None,
) -> str:
    if name == "reminder":
        return await _run_reminder_tool(arguments, reminder_context)
    if name == "set_default_location":
        return await _run_default_location_tool(arguments, location_context)
    return await asyncio.to_thread(_run_plugin_tool_sync, name, arguments, progress)


def _run_skill_view_tool_sync(
    arguments: Mapping[str, Any],
    *,
    available_tools: Sequence[str],
) -> str:
    payload = view_soul_skill(
        str(arguments.get("name") or ""),
        file_path=str(arguments.get("file_path") or "") or None,
        available_tools=available_tools,
    )
    return json.dumps(payload, ensure_ascii=False)


def _map_history(recent_messages: Optional[Sequence[Mapping[str, str]]]) -> List[Dict[str, str]]:
    mapped: List[Dict[str, str]] = []
    for message in recent_messages or []:
        role = message.get("role")
        content = message.get("content")
        if role in ("user", "assistant") and content:
            mapped.append({"role": role, "content": str(content)})
    return mapped[-10:]


async def _chat_completion(
    client: httpx.AsyncClient,
    cfg: Mapping[str, str],
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    *,
    max_tokens_override: Optional[int] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"model": cfg["model"], "messages": messages}
    max_tokens = max_tokens_override if max_tokens_override is not None else settings.soul_agent_max_tokens
    if max_tokens is not None and int(max_tokens) > 0:
        payload["max_tokens"] = int(max_tokens)
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    call_id = record_llm_request(
        source="soul_agent",
        provider=str(cfg.get("provider") or ""),
        model=str(cfg.get("model") or ""),
        base_url=str(cfg.get("base_url") or ""),
        payload=payload,
        attributes={"tools_count": len(tools or [])},
    )
    started_at = time.perf_counter()
    try:
        resp = await client.post(
            cfg["base_url"],
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        elapsed = time.perf_counter() - started_at
        logger.info(
            "[soul_agent] LLM 请求完成: "
            f"provider={cfg.get('provider')}, model={cfg.get('model')}, "
            f"tools={len(tools or [])}, elapsed={elapsed:.2f}s"
        )
        record_llm_response(
            call_id=call_id,
            source="soul_agent",
            provider=str(cfg.get("provider") or ""),
            model=str(cfg.get("model") or ""),
            response={
                "message": message,
                "usage": data.get("usage"),
                "id": data.get("id"),
                "created": data.get("created"),
            },
        )
        return message
    except Exception as exc:
        elapsed = time.perf_counter() - started_at
        logger.warning(
            "[soul_agent] LLM 请求失败: "
            f"provider={cfg.get('provider')}, model={cfg.get('model')}, "
            f"tools={len(tools or [])}, elapsed={elapsed:.2f}s, error={exc}"
        )
        record_llm_response(
            call_id=call_id,
            source="soul_agent",
            provider=str(cfg.get("provider") or ""),
            model=str(cfg.get("model") or ""),
            status="failed",
            error=exc,
        )
        raise


async def _chat_completion_stream_content(
    client: httpx.AsyncClient,
    cfg: Mapping[str, str],
    messages: List[Dict[str, Any]],
    *,
    stream_callback: StreamCallback,
    max_tokens_override: Optional[int] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"model": cfg["model"], "messages": messages, "stream": True}
    max_tokens = max_tokens_override if max_tokens_override is not None else settings.soul_agent_max_tokens
    if max_tokens is not None and int(max_tokens) > 0:
        payload["max_tokens"] = int(max_tokens)
    call_id = record_llm_request(
        source="soul_agent",
        provider=str(cfg.get("provider") or ""),
        model=str(cfg.get("model") or ""),
        base_url=str(cfg.get("base_url") or ""),
        payload=payload,
        attributes={"tools_count": 0, "stream": True},
    )
    started_at = time.perf_counter()
    first_token_elapsed: Optional[float] = None
    content_parts: List[str] = []
    last_chunk_id = ""
    try:
        async with client.stream(
            "POST",
            cfg["base_url"],
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
        ) as resp:
            resp.raise_for_status()
            async for raw_line in resp.aiter_lines():
                line = raw_line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if not line:
                    continue
                if line == "[DONE]":
                    break
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(f"[soul_agent] 忽略无法解析的 stream chunk: {_short_text(line, 120)}")
                    continue
                last_chunk_id = str(chunk.get("id") or last_chunk_id)
                choices = chunk.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                choice = choices[0]
                if not isinstance(choice, Mapping):
                    continue
                delta = choice.get("delta")
                if not isinstance(delta, Mapping):
                    continue
                piece = str(delta.get("content") or "")
                if not piece:
                    continue
                if first_token_elapsed is None:
                    first_token_elapsed = time.perf_counter() - started_at
                    logger.info(
                        "[soul_agent] LLM 首 token 到达: "
                        f"provider={cfg.get('provider')}, model={cfg.get('model')}, "
                        f"elapsed={first_token_elapsed:.2f}s"
                    )
                content_parts.append(piece)
                await stream_callback(piece)

        final_text = "".join(content_parts)
        elapsed = time.perf_counter() - started_at
        logger.info(
            "[soul_agent] LLM 流式请求完成: "
            f"provider={cfg.get('provider')}, model={cfg.get('model')}, "
            f"elapsed={elapsed:.2f}s, first_token={first_token_elapsed or 0:.2f}s"
        )
        record_llm_response(
            call_id=call_id,
            source="soul_agent",
            provider=str(cfg.get("provider") or ""),
            model=str(cfg.get("model") or ""),
            response={
                "message": {"content": final_text},
                "id": last_chunk_id,
                "stream": True,
                "first_token_elapsed": first_token_elapsed,
            },
        )
        return {"content": final_text, "tool_calls": []}
    except Exception as exc:
        elapsed = time.perf_counter() - started_at
        logger.warning(
            "[soul_agent] LLM 流式请求失败: "
            f"provider={cfg.get('provider')}, model={cfg.get('model')}, "
            f"elapsed={elapsed:.2f}s, error={exc}"
        )
        record_llm_response(
            call_id=call_id,
            source="soul_agent",
            provider=str(cfg.get("provider") or ""),
            model=str(cfg.get("model") or ""),
            status="failed",
            error=exc,
        )
        raise


def _is_retryable_agent_error(exc: Exception) -> bool:
    if isinstance(exc, (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.TimeoutException,
        httpx.RemoteProtocolError,
        httpx.NetworkError,
    )):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 408 or status_code == 429 or 500 <= status_code <= 599
    return False


def _retryable_error_label(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


async def _chat_completion_with_network_retry(
    client: httpx.AsyncClient,
    cfg: Mapping[str, str],
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    *,
    progress_callback: Optional[ProgressCallback],
    progress_history: List[Dict[str, Any]],
    retry_budget: NetworkRetryBudget,
    max_tokens_override: Optional[int] = None,
    stream_callback: Optional[StreamCallback] = None,
) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    while True:
        try:
            if tools is None and stream_callback is not None:
                return await _chat_completion_stream_content(
                    client,
                    cfg,
                    messages,
                    stream_callback=stream_callback,
                    max_tokens_override=max_tokens_override,
                )
            return await _chat_completion(
                client,
                cfg,
                messages,
                tools,
                max_tokens_override=max_tokens_override,
            )
        except Exception as exc:
            if not _is_retryable_agent_error(exc):
                raise
            last_error = exc
            if retry_budget.used >= retry_budget.limit:
                break

            retry_budget.used += 1
            retry_number = retry_budget.used
            logger.warning(
                f"[soul_agent] LLM 网络请求失败，准备重试 "
                f"({retry_number}/{retry_budget.limit}): {_retryable_error_label(exc)}"
            )
            await _emit_agent_progress(
                progress_callback,
                history=progress_history,
                phase_key=f"network_retry_{retry_number}",
                phase_label=f"网络不稳，重试查询（{retry_number}/{retry_budget.limit}）",
                description=_retryable_error_label(exc),
                status="running",
                progress=0,
            )
            await asyncio.sleep(_NETWORK_RETRY_DELAYS[min(retry_number - 1, len(_NETWORK_RETRY_DELAYS) - 1)])

    label = _retryable_error_label(last_error) if last_error is not None else "unknown"
    raise SoulAgentNetworkError(
        f"Soul agent LLM 网络请求失败，已重试 {retry_budget.used} 次仍未成功: {label}"
    ) from last_error


def _merge_skill_names(*groups: Sequence[str]) -> List[str]:
    merged: List[str] = []
    for group in groups:
        for name in group:
            if name and name not in merged:
                merged.append(name)
    return merged


def _normalize_guide_text(text: str) -> str:
    normalized = str(text or "").strip()
    for source, target in _GUIDE_DESTINATION_ALIASES.items():
        normalized = normalized.replace(source, target)
    return normalized


def _extract_guide_destination(text: str) -> str:
    normalized = _normalize_guide_text(text)
    for pattern in _GUIDE_DESTINATION_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        dest = str(match.group("dest") or "").strip(" ，。！？,.!?")
        dest = _GUIDE_DESTINATION_ALIASES.get(dest, dest)
        if dest and dest not in _GUIDE_INVALID_DESTINATIONS:
            return dest
    return ""


def _extract_guide_duration(text: str) -> str:
    match = re.search(r"([0-9]{1,2}|[一二三四五六七八九十两]{1,3})\s*(天|日)(?:游)?", str(text or ""))
    if not match:
        return ""
    return re.sub(r"\s+", "", match.group(0))


def _is_guide_fast_path_request(text: str, *, skill_prompt: str) -> bool:
    if "- guide:" not in skill_prompt:
        return False
    normalized = _normalize_guide_text(text)
    if _GUIDE_FAST_TRIGGER_RE.search(normalized) is None:
        return False
    if _GUIDE_FAST_BLOCK_RE.search(normalized) is not None:
        return False
    if _GUIDE_WEB_EXTRACT_ALLOWED_RE.search(normalized) is not None:
        return False
    return bool(_extract_guide_destination(normalized))


def _guide_fast_mode(text: str) -> str:
    normalized = _normalize_guide_text(text)
    return "rich" if _GUIDE_RICH_TRIGGER_RE.search(normalized) is not None else "short"


def _guide_fast_search_args(text: str, *, mode: str) -> Dict[str, Any]:
    normalized = _normalize_guide_text(text)
    destination = _extract_guide_destination(normalized)
    duration = _extract_guide_duration(normalized)
    duration_label = duration or ("3天4天" if mode == "rich" else "通用")
    query_prefix = f"{destination} {duration}".strip()
    route_query = f"{destination} {duration_label} 旅游攻略 经典路线 景点".strip()
    objective = (
        f"为用户整理{destination}{duration or ''}中文旅游攻略参考，覆盖城市气质、核心体验、"
        "经典行程、景点取舍、地道美食、住宿交通和行前贴士；不需要实时天气、车票、票价或营业状态。"
    )
    search_queries = [
        route_query,
        f"{destination} 必去景点 核心体验 怎么玩",
        f"{destination} 必吃美食 小吃 老字号 美食街",
    ]
    if mode == "rich":
        search_queries.append(f"{destination} 住宿区域 交通 预约 注意事项")
    else:
        search_queries.append(f"{destination} 交通 住宿 注意事项")
    return {
        "query": route_query,
        "objective": objective,
        "search_queries": search_queries,
        "limit": 12,
    }


def _guide_fast_system_prompt(final_reply_prompt: str, *, mode: str) -> str:
    parts = [
        "你是 Aini，一个中文陪伴式旅行助手。",
        "你正在处理 guide 泛旅游攻略快链路：已经拿到联网搜索摘要，现在必须直接生成最终中文答复，不要调用工具。",
        "不要声称查询了实时天气、车票、票价、营业状态或本地库存；如果用户需要这些实时信息，提醒需要进一步查询。",
        "不要因为产品面向老人就默认写老人友好攻略；只有用户明确提到老人、父母、长辈、少走路时，才加入适老提醒。",
    ]
    if final_reply_prompt:
        parts.append("## 最终回复风格\n" + final_reply_prompt)
    if mode == "rich":
        parts.append(
            "## 本次攻略输出结构\n"
            "输出要像一份有旅行编辑感的中文攻略，信息丰富但不堆砌。"
            "本段结构优先于上面的“最多给 2-5 条重点”表达规则，但仍要短句自然、适合阅读。\n"
            "必须按以下顺序组织：\n"
            "1. 开场：1 段说明目的地气质和适合玩法。\n"
            "2. 核心体验速览：3 条，每条包含体验主题、为什么值得、适合怎么安排。\n"
            "3. 经典行程参考：如果用户给出天数，按该天数写 Day 1...；如果没给天数，默认给 3-4 天参考。"
            "每天标题必须使用“Day 1：主题”这种格式；每天只写上午/下午/晚上各一句，包含景点和餐饮区域，避免写成纯景点清单。\n"
            "4. 地道美食寻味：用 Markdown 表格，列“必吃美食 / 风味特点 / 寻觅去处”，恰好 4 行。\n"
            "5. 实用行前贴士：交通、住宿区域、预约/门票、季节或物品提醒，恰好 4 条，每条一句。\n"
            "不要在正文插入引用编号或小圆点；不要写“参考来源”“参考链接”“信息来源”等文末来源章节；来源会由系统在回复开头展示为已阅读网页折叠区。\n"
            "必须保证前 5 个部分都完整出现；如果篇幅不够，优先压缩 Day 描述，不得省略美食表或行前贴士。"
            "篇幅目标 1800-2400 个中文字符；不要编造搜索结果没有支持的精确价格、实时营业状态或实时天气。"
        )
    else:
        parts.append(
            "## 本次攻略输出结构\n"
            "输出中等长度攻略，800-1200 个中文字符。"
            "先给一句整体建议，然后按“核心体验、推荐路线、美食住宿、行前贴士”组织。"
            "不要在正文插入引用编号或小圆点；不要写“参考来源”“参考链接”“信息来源”等文末来源章节；来源会由系统在回复开头展示为已阅读网页折叠区。"
        )
    return "\n".join(parts)


async def _try_run_guide_fast_path(
    text: str,
    *,
    cfg: Mapping[str, str],
    skill_prompt: str,
    final_reply_prompt: str,
    recent_messages: Optional[Sequence[Mapping[str, str]]],
    progress_callback: Optional[ProgressCallback],
    reminder_context: Optional[ReminderContext],
    default_location_context: Optional[DefaultLocationContext],
    active_final_skills: Sequence[str],
    stream_callback: Optional[StreamCallback],
) -> Optional[SoulCompanionResult]:
    if not _is_guide_fast_path_request(text, skill_prompt=skill_prompt):
        return None

    progress_history: List[Dict[str, Any]] = []
    guide_mode = _guide_fast_mode(text)
    search_args = _guide_fast_search_args(text, mode=guide_mode)
    await _emit_agent_progress(
        progress_callback,
        history=progress_history,
        phase_key="guide_fast_search",
        phase_label="联网：搜索攻略参考",
        description=_short_text(search_args.get("objective", ""), 160),
        progress=18,
    )

    started_at = time.perf_counter()
    result_str = await _run_tool(
        "web_search",
        search_args,
        reminder_context=reminder_context,
        location_context=default_location_context,
        progress=None,
    )
    search_elapsed = time.perf_counter() - started_at
    try:
        search_payload = json.loads(result_str)
    except json.JSONDecodeError:
        search_payload = {"success": False, "error": result_str}

    if not isinstance(search_payload, Mapping) or not search_payload.get("success"):
        logger.info(
            "[soul_agent] guide 快链路搜索失败，回退普通 agent loop: "
            f"elapsed={search_elapsed:.2f}s, result={_short_text(result_str, 180)}"
        )
        return None

    logger.info(
        "[soul_agent] guide 快链路搜索完成: "
        f"elapsed={search_elapsed:.2f}s, args={_argument_summary(search_args)}, "
        f"result={_short_text(search_payload.get('text', ''), 180)}"
    )
    await _emit_agent_progress(
        progress_callback,
        history=progress_history,
        phase_key="guide_fast_search_complete",
        phase_label="搜索：已拿到攻略参考",
        description=_short_text(search_payload.get("text", ""), 180),
        status="running",
        progress=55,
    )

    web_text = str(search_payload.get("text") or "").strip()
    tool_results = [
        {
            "name": "web_search",
            "arguments": search_args,
            "result": dict(search_payload),
        }
    ]
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": _guide_fast_system_prompt(final_reply_prompt, mode=guide_mode),
        }
    ]
    messages.extend(_map_history(recent_messages)[-4:])
    messages.append(
        {
            "role": "user",
            "content": (
                f"用户问题：{text}\n\n"
                f"联网搜索结果：\n{web_text}\n\n"
                "请基于以上搜索摘要生成最终答复。"
            ),
        }
    )
    await _emit_source_references(progress_callback, tool_results)

    await _emit_agent_progress(
        progress_callback,
        history=progress_history,
        phase_key="guide_fast_final",
        phase_label="整理：生成攻略",
        status="running",
        progress=78,
    )
    async with httpx.AsyncClient(timeout=settings.soul_agent_timeout) as client:
        message = await _chat_completion_with_network_retry(
            client,
            cfg,
            messages,
            tools=None,
            progress_callback=progress_callback,
            progress_history=progress_history,
            retry_budget=NetworkRetryBudget(),
            max_tokens_override=2200 if guide_mode == "rich" else 1000,
            stream_callback=stream_callback,
        )

    final_text = str(message.get("content") or "")
    await _emit_agent_progress(
        progress_callback,
        history=progress_history,
        phase_key="final_answer",
        phase_label="整理：生成回复",
        description=_short_text(final_text, 180),
        status="success",
        progress=100,
    )
    result = _finalize(
        final_text,
        cfg,
        ["web_search"],
        tool_results,
        active_skills=_merge_skill_names(["guide"], active_final_skills),
    )
    result.artifact["fast_path"] = "guide"
    result.artifact["guide_mode"] = guide_mode
    result.artifact["fast_path_elapsed"] = {"web_search": round(search_elapsed, 3)}
    return result


def _direct_health_result_text(
    used_tools: Sequence[str],
    tool_results: Optional[Sequence[Mapping[str, Any]]],
) -> str:
    if list(used_tools) != ["health_query"]:
        return ""
    health_results = [
        item for item in (tool_results or [])
        if item.get("name") == "health_query"
    ]
    if len(health_results) != 1:
        return ""
    result = health_results[0].get("result")
    if not isinstance(result, Mapping) or not result.get("success"):
        return ""
    result_text = str(result.get("text") or "").strip()
    if result_text:
        return result_text
    return ""


def _sanitize_health_reply(text: str, used_tools: Sequence[str]) -> str:
    if "health_query" not in used_tools:
        return text
    forbidden = re.compile(
        r"(降压药|药物|吃药|服药|停药|用药|处方|"
        r"正常范围|正常水平|正常现象|控制得不错|身体状态不错|"
        r"您放心|不用担心|挺好的|很不错|控制血压|"
        r"规律作息|清淡饮食|低盐|少盐|饮食|锻炼|运动|血压稳定)"
    )
    sentence_pattern = re.compile(r"[^。！？!?；;]+[。！？!?；;]?")
    lines: List[str] = []
    for line in text.splitlines():
        if not forbidden.search(line):
            lines.append(line)
            continue
        sentences = sentence_pattern.findall(line)
        kept = [sentence.strip() for sentence in sentences if not forbidden.search(sentence)]
        if kept:
            lines.append("".join(kept))
    cleaned = "\n".join(lines).strip()
    return cleaned or text


def _reference_label_for_url(url: str) -> str:
    host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", url, flags=re.IGNORECASE).split("/", 1)[0])
    known = {
        "gov.cn": "中国政府网",
        "www.gov.cn": "中国政府网",
        "cctv.com": "央视网",
        "news.cctv.com": "央视网",
        "nhsa.gov.cn": "国家医保局",
        "www.nhsa.gov.cn": "国家医保局",
        "12306.cn": "12306",
        "kyfw.12306.cn": "12306",
    }
    return known.get(host, host or "参考链接")


def _append_public_reference(
    references: List[Dict[str, str]],
    seen: set[str],
    label: str,
    url: str,
) -> None:
    clean_url = str(url or "").strip().rstrip(".,，。；;、")
    if not clean_url.startswith(("http://", "https://")) or clean_url in seen:
        return
    seen.add(clean_url)
    safe_label = str(label or "").replace("[", "").replace("]", "").strip()
    references.append({
        "label": safe_label or _reference_label_for_url(clean_url),
        "url": clean_url,
    })


def _collect_public_references_from_value(
    value: Any,
    references: List[Dict[str, str]],
    seen: set[str],
    *,
    depth: int = 0,
    limit: int = 12,
) -> None:
    if depth > 8 or len(references) >= limit:
        return
    if isinstance(value, list):
        for item in value:
            _collect_public_references_from_value(item, references, seen, depth=depth + 1, limit=limit)
            if len(references) >= limit:
                return
        return
    if not isinstance(value, Mapping):
        return

    raw_url = value.get("url")
    if isinstance(raw_url, str):
        label = ""
        for key in ("title", "name", "label", "source"):
            raw_label = value.get(key)
            if isinstance(raw_label, str) and raw_label.strip():
                label = raw_label.strip()
                break
        _append_public_reference(references, seen, label, raw_url)

    for key, child in value.items():
        if str(key).lower() in {"content", "text", "description", "markdown", "raw", "trace", "logs", "messages", "prompt"}:
            continue
        if isinstance(child, (dict, list)):
            _collect_public_references_from_value(child, references, seen, depth=depth + 1, limit=limit)
            if len(references) >= limit:
                return


def _public_references_from_tool_results(
    tool_results: Optional[Sequence[Mapping[str, Any]]],
    *,
    limit: int = 12,
) -> List[Dict[str, str]]:
    references: List[Dict[str, str]] = []
    seen: set[str] = set()
    for item in tool_results or []:
        name = str(item.get("name") or "")
        if name not in {"web_search", "web_extract"}:
            continue
        _collect_public_references_from_value(item.get("result"), references, seen, limit=limit)
        if len(references) >= limit:
            break
    return references


async def _emit_source_references(
    progress_callback: Optional[ProgressCallback],
    tool_results: Optional[Sequence[Mapping[str, Any]]],
) -> None:
    if progress_callback is None:
        return
    references = _public_references_from_tool_results(tool_results)
    if not references:
        return
    try:
        await progress_callback({
            "type": "assistant_sources",
            "references": references,
        })
    except Exception as exc:
        logger.warning(f"[soul_agent] 来源事件发送失败: {exc}")


def _finalize(
    text: str,
    cfg: Mapping[str, str],
    used_tools: List[str],
    tool_results: Optional[List[Dict[str, Any]]] = None,
    active_skills: Optional[Sequence[str]] = None,
) -> SoulCompanionResult:
    ordered = list(dict.fromkeys(used_tools))
    ordered_skills = list(dict.fromkeys(active_skills or []))
    final = (
        _direct_health_result_text(used_tools, tool_results)
        or (text or "").strip()
        or "我这边暂时没整理出结果，您换个说法再问我一次好吗？"
    )
    final = _sanitize_health_reply(final, used_tools)
    source = "soul_companion:agent"
    if ordered:
        source += ":" + ",".join(ordered)
    return SoulCompanionResult(
        text=final,
        source=source,
        artifact={
            "tool": "soul_companion_agent",
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "tools_used": ordered,
            "skills_used": ordered_skills,
            "status": "success",
            "tool_results": tool_results or [],
        },
    )


def _is_blocked_tool_call(
    name: str,
    *,
    loaded_skills: Sequence[str],
    user_text: str,
    used_tools: Sequence[str],
) -> bool:
    if "guide" not in loaded_skills:
        return False
    if _GUIDE_WEB_EXTRACT_ALLOWED_RE.search(user_text) is not None:
        return False
    if name == "web_extract":
        return True
    if name == "web_search":
        return list(used_tools).count("web_search") >= 2
    return False


async def run_soul_agent(
    text: str,
    *,
    recent_messages: Optional[Sequence[Mapping[str, str]]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    stream_callback: Optional[StreamCallback] = None,
    reminder_context: Optional[ReminderContext] = None,
    default_location_context: Optional[DefaultLocationContext] = None,
) -> SoulCompanionResult:
    """Drive the soul_* tools with an LLM tool-calling loop.

    Raises on configuration/transport errors so the caller can report an agent
    failure without trying to re-route the request heuristically.
    """
    cfg = _resolve_provider()
    if not cfg["api_key"]:
        raise RuntimeError(f"Soul agent 未配置 {cfg['provider']} API Key")

    tools = _build_tools()
    tool_names = [
        str(tool.get("function", {}).get("name") or "")
        for tool in tools
        if isinstance(tool.get("function"), Mapping)
    ]
    skill_context = build_soul_skill_index_prompt(available_tools=tool_names)
    reply_humanizer = build_reply_humanizer_prompt()
    if reply_humanizer.active_skills:
        logger.info(
            "[soul_agent] 最终回复启用 inline runtime skills: "
            f"{', '.join(reply_humanizer.active_skills)}"
        )
    guide_fast_result = await _try_run_guide_fast_path(
        text,
        cfg=cfg,
        skill_prompt=skill_context.prompt,
        final_reply_prompt=reply_humanizer.prompt,
        recent_messages=recent_messages,
        progress_callback=progress_callback,
        reminder_context=reminder_context,
        default_location_context=default_location_context,
        active_final_skills=reply_humanizer.active_skills,
        stream_callback=stream_callback,
    )
    if guide_fast_result is not None:
        return guide_fast_result

    max_turns = max(1, int(settings.soul_agent_max_turns))
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": _system_prompt(
                default_location_context,
                skill_prompt=skill_context.prompt,
                final_reply_prompt=reply_humanizer.prompt,
            ),
        }
    ]
    messages.extend(_map_history(recent_messages))
    messages.append({"role": "user", "content": text})

    used_tools: List[str] = []
    loaded_skills: List[str] = []
    tool_results: List[Dict[str, Any]] = []
    progress_history: List[Dict[str, Any]] = []
    retry_budget = NetworkRetryBudget()
    tool_concurrency = max(1, int(settings.soul_agent_tool_concurrency))
    async with httpx.AsyncClient(timeout=settings.soul_agent_timeout) as client:
        for _turn in range(max_turns):
            await _emit_agent_progress(
                progress_callback,
                history=progress_history,
                phase_key=f"model_turn_{_turn + 1}",
                phase_label="判断：选择查询方式" if _turn == 0 else "审核：整理查询结果",
                description=f"provider={cfg['provider']}",
                progress=min(8 + _turn * 18, 86),
            )
            message = await _chat_completion_with_network_retry(
                client,
                cfg,
                messages,
                tools,
                progress_callback=progress_callback,
                progress_history=progress_history,
                retry_budget=retry_budget,
            )
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                final_text = str(message.get("content") or "")
                await _emit_source_references(progress_callback, tool_results)
                await _emit_agent_progress(
                    progress_callback,
                    history=progress_history,
                    phase_key="final_answer",
                    phase_label="整理：生成回复",
                    description=_short_text(message.get("content", ""), 180),
                    status="success",
                    progress=100,
                )
                return _finalize(
                    final_text,
                    cfg,
                    used_tools,
                    tool_results,
                    active_skills=_merge_skill_names(
                        loaded_skills,
                        reply_humanizer.active_skills,
                    ),
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )
            prepared_tool_calls: List[Dict[str, Any]] = []
            for call in tool_calls:
                fn = call.get("function", {}) or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments") or "{}"
                try:
                    arguments = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                prepared_tool_calls.append({"call": call, "name": name, "arguments": arguments})
                tool_description = _tool_schema_description(name)
                await _emit_agent_progress(
                    progress_callback,
                    history=progress_history,
                    phase_key=f"tool_start_{name}",
                    phase_label=_tool_start_label(name, arguments),
                    description=tool_description,
                    progress=min(18 + len(progress_history) * 10, 92),
                )

            tool_semaphore = asyncio.Semaphore(tool_concurrency)

            async def run_prepared_tool(prepared: Mapping[str, Any]) -> Dict[str, Any]:
                name = str(prepared.get("name") or "")
                arguments = prepared.get("arguments")
                if not isinstance(arguments, Mapping):
                    arguments = {}
                progress_labels: List[str] = []

                async with tool_semaphore:
                    started_at = time.perf_counter()
                    blocked = _is_blocked_tool_call(
                        name,
                        loaded_skills=loaded_skills,
                        user_text=text,
                        used_tools=used_tools,
                    )
                    if blocked:
                        error = (
                            "guide skill 场景默认不读取网页正文；"
                            "请基于已有 web_search 摘要直接整理攻略。"
                        )
                        if name == "web_search":
                            error = (
                                "guide skill 场景最多执行 2 次 web_search；"
                                "请基于已有搜索摘要直接整理攻略。"
                            )
                        result_str = json.dumps(
                            {
                                "success": False,
                                "error": error,
                                "blocked_tool": name,
                                "source": "skill_policy",
                            },
                            ensure_ascii=False,
                        )
                    elif name == "skill_view":
                        result_str = await asyncio.to_thread(
                            _run_skill_view_tool_sync,
                            arguments,
                            available_tools=tool_names,
                        )
                    else:
                        result_str = await _run_tool(
                            name,
                            arguments,
                            reminder_context=reminder_context,
                            location_context=default_location_context,
                            progress=None,
                        )
                    elapsed = time.perf_counter() - started_at
                    result_success, result_summary = _tool_result_summary(result_str)
                    logger.info(
                        "[soul_agent] 工具执行完成: "
                        f"tool={name}, success={result_success}, elapsed={elapsed:.2f}s, "
                        f"args={_argument_summary(arguments)}, result={result_summary}"
                    )
                return {
                    "call": prepared.get("call"),
                    "name": name,
                    "arguments": dict(arguments),
                    "result": result_str,
                    "progress_labels": progress_labels,
                    "blocked": blocked,
                }

            executed_tools = await asyncio.gather(
                *(run_prepared_tool(prepared) for prepared in prepared_tool_calls)
            )

            for executed in executed_tools:
                call = executed.get("call")
                name = str(executed.get("name") or "")
                arguments = executed.get("arguments")
                if not isinstance(arguments, Mapping):
                    arguments = {}
                result_str = str(executed.get("result") or "")
                blocked = bool(executed.get("blocked"))
                if name != "skill_view" and not blocked:
                    used_tools.append(name)
                for label in executed.get("progress_labels") or []:
                    await _emit_agent_progress(
                        progress_callback,
                        history=progress_history,
                        phase_key=f"tool_detail_{name}",
                        phase_label=str(label),
                        progress=min(22 + len(progress_history) * 10, 94),
                    )
                try:
                    result_payload = json.loads(result_str)
                except json.JSONDecodeError:
                    result_payload = {"text": result_str}
                if isinstance(result_payload, Mapping):
                    if name == "skill_view" and result_payload.get("success"):
                        loaded_name = str(result_payload.get("name") or "").strip()
                        if loaded_name and loaded_name not in loaded_skills:
                            loaded_skills.append(loaded_name)
                            logger.info(f"[soul_agent] 已加载 runtime skill: {loaded_name}")
                    if not blocked:
                        artifact_payload = dict(result_payload)
                        if name == "skill_view":
                            artifact_payload.pop("content", None)
                        tool_results.append(
                            {
                                "name": name,
                                "arguments": dict(arguments),
                                "result": artifact_payload,
                            }
                        )
                result_success, result_summary = _tool_result_summary(result_str)
                await _emit_agent_progress(
                    progress_callback,
                    history=progress_history,
                    phase_key=f"tool_complete_{name}",
                    phase_label=_tool_complete_label(name, result_success),
                    description=result_summary,
                    status="running" if result_success else "failed",
                    progress=min(28 + len(progress_history) * 10, 96),
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") if isinstance(call, Mapping) else None,
                        "name": name,
                        "content": result_str,
                    }
                )

        # Tool budget exhausted: force a final answer without further tool calls.
        logger.info(f"[soul_agent] 达到 max_turns={max_turns}，强制收尾输出")
        messages.append(
            {
                "role": "user",
                "content": "请根据以上已查询到的结果，直接给出最终中文答复，不要再调用工具。",
            }
        )
        await _emit_agent_progress(
            progress_callback,
            history=progress_history,
            phase_key="force_final_answer",
            phase_label="整理：汇总已查结果",
            status="running",
            progress=96,
        )
        await _emit_source_references(progress_callback, tool_results)
        message = await _chat_completion_with_network_retry(
            client,
            cfg,
            messages,
            tools=None,
            progress_callback=progress_callback,
            progress_history=progress_history,
            retry_budget=retry_budget,
            stream_callback=stream_callback,
        )
        final_text = str(message.get("content") or "")
        await _emit_agent_progress(
            progress_callback,
            history=progress_history,
            phase_key="final_answer",
            phase_label="整理：生成回复",
            description=_short_text(message.get("content", ""), 180),
            status="success",
            progress=100,
        )
        return _finalize(
            final_text,
            cfg,
            used_tools,
            tool_results,
            active_skills=_merge_skill_names(
                loaded_skills,
                reply_humanizer.active_skills,
            ),
        )
