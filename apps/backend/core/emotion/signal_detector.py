"""
情绪信号检测器

输入文本 → 输出 EmotionSignals，Phase 1 关键词通道。
"""

from __future__ import annotations

from typing import List

from core.emotion.signals import EmotionSignals

# Phase 1 关键词映射表
_SADNESS_KEYWORDS: List[str] = [
    "难过", "伤心", "想念", "老伴", "走了", "一个人", "冷清", "孤独", "寂寞",
    "不开心", "不高兴", "不太好", "不是很好", "不舒服", "郁闷", "低落",
    "委屈", "苦恼", "心烦", "闷闷不乐", "不快乐",
]
_ANXIETY_KEYWORDS: List[str] = [
    "担心", "害怕", "焦虑", "紧张", "不安", "着急",
]
_ANGER_KEYWORDS: List[str] = [
    "生气", "愤怒", "烦", "讨厌", "气死",
]
_URGENCY_KEYWORDS: List[str] = [
    "救命", "急救", "120", "心脏", "摔倒", "晕倒", "出血",
]


class SignalDetector:
    """
    多通道信号聚合器。
    Phase 1: 文本关键词通道。
    输出 EmotionSignals，不输出 emotion_label。
    """

    def __init__(
        self,
        sadness_keywords: List[str] | None = None,
        anxiety_keywords: List[str] | None = None,
        anger_keywords: List[str] | None = None,
        urgency_keywords: List[str] | None = None,
    ) -> None:
        self._sadness_kw = sadness_keywords or _SADNESS_KEYWORDS
        self._anxiety_kw = anxiety_keywords or _ANXIETY_KEYWORDS
        self._anger_kw = anger_keywords or _ANGER_KEYWORDS
        self._urgency_kw = urgency_keywords or _URGENCY_KEYWORDS

    async def detect(self, text: str) -> EmotionSignals:
        """
        检测文本中的情绪信号。

        Args:
            text: 用户输入的文本

        Returns:
            EmotionSignals: 纯数值信号结构体
        """
        keyword_hits: List[str] = []

        sadness_hits = [kw for kw in self._sadness_kw if kw in text]
        anxiety_hits = [kw for kw in self._anxiety_kw if kw in text]
        anger_hits = [kw for kw in self._anger_kw if kw in text]
        urgency_hits = [kw for kw in self._urgency_kw if kw in text]

        keyword_hits.extend(sadness_hits)
        keyword_hits.extend(anxiety_hits)
        keyword_hits.extend(anger_hits)
        keyword_hits.extend(urgency_hits)

        sadness_score = min(len(sadness_hits) * 0.3, 1.0)
        anxiety_score = min(len(anxiety_hits) * 0.3, 1.0)
        anger_score = min(len(anger_hits) * 0.3, 1.0)
        urgency_flag = len(urgency_hits) > 0

        signals = EmotionSignals(
            sadness_score=sadness_score,
            anxiety_score=anxiety_score,
            anger_score=anger_score,
            energy_level=0.5,
            speech_rate=0.5,
            urgency_flag=urgency_flag,
            keyword_hits=keyword_hits,
        )
        return signals
