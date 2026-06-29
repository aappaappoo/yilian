"""
人设框架

PersonaConfig 数据模型 + YAML 加载器。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field
from loguru import logger
from core.logging_utils import STARTUP


class PersonaLoadError(Exception):
    """人设加载异常。"""


# ── 上下文管理子模型 ──

class ImportantEventsConfig(BaseModel):
    """重要事件提取配置"""
    enabled: bool = True
    event_categories: List[str] = Field(default_factory=list)
    extraction_prompt: str = ""


class SummaryConfig(BaseModel):
    """摘要生成配置"""
    enabled: bool = True
    summary_prompt: str = ""


class ContextManagementConfig(BaseModel):
    """上下文管理配置"""
    max_context_messages: Optional[int] = Field(default=None, description="对话记录截断条数，None 表示使用全局 ENV 配置")
    summary_limit: Optional[int] = Field(default=None, description="上下文同步时注入的摘要条数，None 表示使用全局 ENV 配置")
    events_limit: Optional[int] = Field(default=None, description="上下文同步时注入的事件条数，None 表示使用全局 ENV 配置")
    important_events: ImportantEventsConfig = Field(default_factory=ImportantEventsConfig)
    summary: SummaryConfig = Field(default_factory=SummaryConfig)


class PersonaConfig(BaseModel):
    """人设配置数据模型。"""

    name: str = ""
    role: str = ""
    tone: str = ""
    max_reply_length: int = Field(default=2, description="最大回复长度（句数）")
    voice: str = ""
    tts_model: str = ""
    language: str = ""
    greeting: str = ""
    greetings: List[str] = Field(default_factory=list)
    personality_traits: List[str] = Field(default_factory=list)
    forbidden_topics: List[str] = Field(default_factory=list)
    context_management: Optional[ContextManagementConfig] = Field(
        default=None,
        description="上下文管理配置（摘要 + 重要事件）",
    )
    skill_retry_count: int = Field(default=2, description="Audience Skill LLM 调用失败时的最大重试次数（可在 persona.yaml 中覆盖）")
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    avatar_image: str = ""         # 头像/卡片图片文件名（相对于 audience 目录的 assets/ 子目录）
    vrm_model: str = ""            # VRM 3D 模型文件名（可选，相对于 audience 目录的 assets/ 子目录）
    description: str = ""         # 人物描述/简介

    def to_system_prompt(self) -> str:
        """生成系统提示词。"""
        parts = []
        if self.name:
            parts.append(f"你的名字是{self.name}。")
        if self.role:
            parts.append(f"你的角色是{self.role}。")
        if self.tone:
            parts.append(f"语气风格：{self.tone}。")
        if self.personality_traits:
            parts.append(f"性格特征：{'、'.join(self.personality_traits)}。")
        if self.forbidden_topics:
            parts.append(f"禁止讨论以下话题：{'、'.join(self.forbidden_topics)}。")
        if self.max_reply_length:
            parts.append(f"每次回复不超过{self.max_reply_length}句话。")
        prompt = "\n".join(parts)
        return prompt


def validate_persona(config: Dict[str, Any]) -> List[str]:
    """校验人设配置，返回错误列表。"""
    errors: List[str] = []
    if not config.get("name"):
        errors.append("name is required")
    if not config.get("role"):
        errors.append("role is required")
    return errors


def load_persona(path: str | Path) -> PersonaConfig:
    """
    从 YAML 文件加载人设配置。

    Args:
        path: YAML 文件路径

    Returns:
        PersonaConfig 实例

    Raises:
        PersonaLoadError: 加载失败
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        raise PersonaLoadError(f"Failed to load persona from {path}: {e}") from e

    known_fields = {
        "name", "role", "tone", "max_reply_length", "voice","tts_model",
        "language", "greeting", "greetings", "personality_traits",
        "forbidden_topics", "context_management", "skill_retry_count",
        "avatar_image", "vrm_model", "description",
    }
    custom = {k: v for k, v in data.items() if k not in known_fields}

    kwargs: Dict[str, Any] = {}
    for field_name in known_fields:
        if field_name in data:
            kwargs[field_name] = data[field_name]
    kwargs["custom_fields"] = custom

    persona = PersonaConfig(**kwargs)
    logger.info(
        f"[{STARTUP}] load_persona: path={path}, name='{persona.name}', role='{persona.role}', "
        f"voice='{persona.voice}', traits={persona.personality_traits}, forbidden={persona.forbidden_topics}"
    )
    return persona
