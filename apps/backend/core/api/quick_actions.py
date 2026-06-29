"""LLM-generated quick action suggestions for the chat page."""

from __future__ import annotations

import json
import re
from typing import Literal

import httpx
from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel, Field

from core.config import settings
from core.llm_trace import record_llm_request, record_llm_response
from core.logging_utils import AI_REPLY, flatten_content

router = APIRouter(prefix="/api/quick-actions", tags=["quick-actions"])

MAX_ACTIONS = 4
MAX_MESSAGES = 8
MAX_MESSAGE_CHARS = 700
MAX_ACTION_CHARS = 18
BLOCKED_ACTION_PATTERNS = (
    r"鞋",
    r"鞋子.*哪",
    r"哪双",
    r"选哪个",
    r"哪个车次",
    r"先去哪",
    r"哪一家",
    r"优先级",
)


class QuickActionMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(default="", max_length=MAX_MESSAGE_CHARS)


class QuickActionSuggestionRequest(BaseModel):
    audience: str = Field(default="Aini")
    messages: list[QuickActionMessage] = Field(default_factory=list, max_length=MAX_MESSAGES)
    limit: int = Field(default=MAX_ACTIONS, ge=1, le=MAX_ACTIONS)


class QuickActionSuggestionResponse(BaseModel):
    actions: list[str]
    source: str = "quick_actions_llm"


def _trim_chars(value: str, max_chars: int) -> str:
    return "".join(list(value)[:max_chars])


def _normalize_action(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^[\s\d一二三四五六七八九十]+[.、)\-：:\s]*", "", text)
    text = re.sub(r"\s+", "", text)
    text = text.strip("\"'“”‘’。！？!?")
    if not text or "actions" in text.lower() or re.search(r"[\{\}\[\]]", text):
        return ""
    if any(re.search(pattern, text) for pattern in BLOCKED_ACTION_PATTERNS):
        return ""
    return _trim_chars(text, MAX_ACTION_CHARS)


def _dedupe_actions(values: list[object], limit: int) -> list[str]:
    actions: list[str] = []
    for value in values:
        action = _normalize_action(value)
        if not action or action in actions:
            continue
        actions.append(action)
        if len(actions) >= limit:
            break
    return actions


def _extract_actions(content: str, limit: int) -> list[str]:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
        if not match:
            quoted = re.findall(r'["“]([^"“”\n]{2,40})["”]', text)
            return _dedupe_actions([item for item in quoted if item.lower() not in {"actions", "suggestions"}] or text.splitlines(), limit)
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            quoted = re.findall(r'["“]([^"“”\n]{2,40})["”]', text)
            return _dedupe_actions([item for item in quoted if item.lower() not in {"actions", "suggestions"}] or text.splitlines(), limit)

    if isinstance(parsed, dict):
        raw_actions = parsed.get("actions") or parsed.get("suggestions") or []
    elif isinstance(parsed, str):
        return _extract_actions(parsed, limit)
    else:
        raw_actions = parsed
    return _dedupe_actions(raw_actions if isinstance(raw_actions, list) else [], limit)


def _conversation_for_prompt(messages: list[QuickActionMessage]) -> str:
    if not messages:
        return "暂无对话。用户刚进入聊天页，需要先看到几条自己可能会问 Aini 的问题或请求。"
    lines: list[str] = []
    for message in messages[-MAX_MESSAGES:]:
        text = _trim_chars(message.text.strip(), MAX_MESSAGE_CHARS)
        if not text:
            continue
        speaker = "用户" if message.role == "user" else "Aini"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines) or "暂无对话。请给新用户生成适合作为聊天入口的提示气泡。"


async def _call_quick_actions_llm(request: QuickActionSuggestionRequest) -> list[str]:
    api_key = settings.memory_llm_api_key or settings.dashscope_api_key
    if not settings.quick_actions_llm_enabled or not api_key:
        return []

    system_prompt = (
        "你是 Soulmeet/Aini 聊天页的提示气泡生成器。"
        "请根据最近对话生成用户下一步可能会问 Aini 的中文问题或请求。"
        "这些短句是给不知道问什么的用户看的，必须像用户自己会输入的话，而不是 Aini 对用户说的话。"
        "不要生成寒暄式反问，例如：今天过得好吗、想出去走走吗、中午想吃啥、要我提醒你吗。"
        "必须围绕用户/老人/家属视角，句子要自然、日常、可直接发送。"
        "任务可以自然落到：关怀提醒、核实信息、天气穿衣、吃点什么、轻松出门/旅游规划、车票出行。"
        "如果暂无对话，要生成用户可能主动问的问题，例如：明天适合出门吗？附近有什么清淡餐厅？周末去哪走走不累？长护险怎么申请？"
        "如果已有对话，要顺着上下文生成下一步问题，例如天气后可以问：明天有雷电预警吗？附近有室内景点吗？雨天出门要注意什么？"
        "每条 6 到 18 个汉字左右，不要 emoji，不要编号，不要解释。"
        "允许自然使用：查、推荐、规划、帮我；但不要像功能菜单或后台任务名。"
        "不要生成过细、突兀或像替用户做选择的句子，例如：鞋子穿哪双、先去哪一家、选哪个车次。"
        "只返回 JSON：{\"actions\":[\"短句1\",\"短句2\",\"短句3\",\"短句4\"]}。"
    )
    user_prompt = (
        f"角色: {request.audience or 'Aini'}\n"
        f"请生成 {request.limit + 2} 条备选，系统会筛选展示 {request.limit} 条。\n"
        f"最近对话:\n{_conversation_for_prompt(request.messages)}"
    )
    payload = {
        "model": settings.quick_actions_llm_model or settings.memory_llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.35,
        "max_tokens": 260,
    }
    timeout = max(1.0, min(settings.quick_actions_llm_timeout, settings.memory_llm_timeout))
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    model = str(payload["model"])
    call_id = record_llm_request(
        source="quick_actions",
        provider="dashscope_compatible",
        model=model,
        base_url=settings.memory_llm_base_url,
        payload=payload,
        attributes={"limit": request.limit, "audience": request.audience},
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(settings.memory_llm_base_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            record_llm_response(
                call_id=call_id,
                source="quick_actions",
                provider="dashscope_compatible",
                model=model,
                response={
                    "status_code": response.status_code,
                    "data": data,
                },
            )
        except Exception as exc:
            record_llm_response(
                call_id=call_id,
                source="quick_actions",
                provider="dashscope_compatible",
                model=model,
                status="failed",
                error=exc,
            )
            raise
    content = str(data.get("choices", [{}])[0].get("message", {}).get("content") or "")
    return _extract_actions(content, request.limit)


@router.post("/suggestions", response_model=QuickActionSuggestionResponse)
async def quick_action_suggestions(request: QuickActionSuggestionRequest) -> QuickActionSuggestionResponse:
    try:
        actions = await _call_quick_actions_llm(request)
    except Exception as exc:
        logger.warning(
            f"[{AI_REPLY}] | Task=提示气泡生成 | LLM失败: {type(exc).__name__}: {exc}, "
            f"context='{flatten_content(_conversation_for_prompt(request.messages), max_len=80)}'"
        )
        actions = []
    return QuickActionSuggestionResponse(actions=actions)
