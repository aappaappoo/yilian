"""
SentenceSplitter — 流式文本按句切分工具。

接收流式文本 token，按照标点符号切分成句子。
设计目标：LLM → 按句切分 → TTS，最小化首音延迟（TTFB）。

切分规则（按优先级）：
  1. 硬标点（。！？!?.\n;；～~）—— 所有句子通用
  2. 软标点（，,）—— 仅首句（降低首音延迟）

用法示例::

    splitter = SentenceSplitter()
    for token in llm_stream():
        for sentence in splitter.push(token):
            await tts.synthesize(sentence)
    remaining = splitter.flush()
    if remaining:
        await tts.synthesize(remaining)
"""

from __future__ import annotations

from typing import List, Optional

# 硬标点正则：所有句子均以此切分（含中文口语常用的波浪号）
_HARD_PUNCT = set("。！？!?.\n;；～~")

# 软标点正则：仅首句使用，降低首音延迟
_SOFT_PUNCT = set("，,")


class SentenceSplitter:
    """
    流式文本句子切分器。

    本类为无 IO、纯内存的工具类，可独立于 Pipecat 框架使用。
    每个 LLM 响应开始时通过 ``reset()`` 或 ``flush()`` 重置状态，
    以确保首句软切分阈值正确生效。

    Args:
        force_split_threshold: 可选 TTS 边界配置；未传入时不按长度切分。
    """

    def __init__(self, force_split_threshold: Optional[int] = None) -> None:
        self._buffer: str = ""
        self._is_first_sentence: bool = True
        self._force_split_threshold: Optional[int] = force_split_threshold

    # ── 公开 API ──────────────────────────────────────────────────────────────

    @property
    def buffer(self) -> str:
        """返回当前缓冲区内容（尚未切分的部分），已 strip 首尾空白。"""
        return self._buffer.strip(" ")

    def push(self, text: str) -> List[str]:
        """
        追加文本片段，返回此次切分出的所有完整句子列表（可能为空）。

        Args:
            text: 新到达的文本 token（可以是单字、词或任意长度片段）。

        Returns:
            完整句子列表，每句均已 strip 首尾空白；若尚无完整句则返回空列表。
        """
        self._buffer += text
        return self._extract_all()

    def flush(self) -> Optional[str]:
        """
        流结束时调用，返回缓冲区内剩余文本（已 strip），并重置状态。

        Returns:
            剩余文本字符串；若缓冲区为空则返回 None。
        """
        text = self._buffer.strip()
        self._reset_state()
        return text if text else None

    def reset(self) -> None:
        """
        中断（interruption）或新响应开始时调用，清空缓冲区并重置首句状态。
        """
        self._reset_state()

    # ── 内部实现 ───────────────────────────────────────────────────────────────

    def _reset_state(self) -> None:
        self._buffer = ""
        self._is_first_sentence = True

    def _extract_all(self) -> List[str]:
        """反复提取直到无法继续切分。"""
        sentences: List[str] = []
        while True:
            sentence = self._try_extract_one()
            if sentence is None:
                break
            sentences.append(sentence)
        return sentences

    def _try_extract_one(self) -> Optional[str]:
        """
        尝试从缓冲区提取一个完整句子。

        检查顺序（首句 vs 非首句）：
          首句：比较软、硬标点位置，取较早者；若均无则按长度阈值切分。
          非首句：仅检查硬标点，再按长度阈值切分。

        Returns:
            提取的句子字符串（已 strip），或 None（无法切分）。
        """
        hard_end = _first_punctuation_end(self._buffer, _HARD_PUNCT)

        if self._is_first_sentence:
            soft_end = _first_punctuation_end(self._buffer, _SOFT_PUNCT)
            if soft_end is not None and (hard_end is None or soft_end <= hard_end):
                return self._consume(soft_end)

        if hard_end is not None:
            return self._consume(hard_end)

        if self._force_split_threshold is not None and len(self._buffer) >= self._force_split_threshold:
            return self._consume(self._force_split_threshold)

        return None

    def _consume(self, end: int) -> Optional[str]:
        """
        从缓冲区消费前 ``end`` 个字符作为一个句子，更新首句状态。

        Args:
            end: 消费的字符数。

        Returns:
            提取的句子字符串（已 strip）；若消费结果为空白则返回 None。
        """
        sentence = self._buffer[:end].strip()
        self._buffer = self._buffer[end:]
        if sentence:
            self._is_first_sentence = False
            return sentence
        return None


def _first_punctuation_end(text: str, marks: set[str]) -> Optional[int]:
    for index, char in enumerate(text):
        if char in marks:
            return index + 1
    return None
