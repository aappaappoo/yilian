"""
情绪信号数据类

EmotionSignals — 底座产出的纯数值信号（不含 label）
EmotionDecision — 插件产出的结构化决策
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class EmotionSignals:
    """
    情绪信号（底座产出）。
    所有字段都是无语义的原始数值/布尔/列表。
    底座永远不输出 label。

    Phase 1: 仅 keyword_hits 通道填充有意义值，其余默认。
    Phase 2: + 语义模型通道 → sadness/anxiety/anger 更精确。
    Phase 3: + 音频情感通道 → energy_level/speech_rate 来自实际音频分析。
    """

    sadness_score: float = 0.0
    """悲伤信号强度 [0.0, 1.0]"""

    anxiety_score: float = 0.0
    """焦虑信号强度 [0.0, 1.0]"""

    anger_score: float = 0.0
    """愤怒信号强度 [0.0, 1.0]"""

    energy_level: float = 0.5
    """语音能量水平 [0.0, 1.0]，0.5 为默认中等"""

    speech_rate: float = 0.5
    """语速（标准化）[0.0, 1.0]，0.5 为默认正常"""

    urgency_flag: bool = False
    """紧急情况标记（关键词命中严重词汇时置 True）"""

    keyword_hits: List[str] = field(default_factory=list)
    """命中的关键词列表（如 ["想念", "老伴"]）"""


@dataclass
class EmotionDecision:
    """
    情绪决策（底座定义结构）。

    每个字段都有明确的消费者:
    - label              → 日志/监控/用户画像
    - hint               → 运行时可用于前端提示或后续策略
    - priority           → 情绪策略优先级
    - block_tools        → 预留给工具调用策略
    - tone               → Pipeline 调整 TTS 参数
    """
    label: str = "neutral"
    hint: str = ""
    priority: float = 0.0
    block_tools: List[str] = field(default_factory=list)
    tone: str = ""
