"""
中文增强的文本聚合器。

基于 SentenceSplitter 实现流式句子切分，替代原先基于 NLTK lookahead 的方案。
切分规则：
  - 硬标点（。！？!?.\n;；～~）—— 立即切分，无需 lookahead
  - 软标点（，,）—— 仅首句使用，降低首音延迟（TTFB）
"""

from typing import AsyncIterator, Optional

from pipecat.utils.text.base_text_aggregator import Aggregation, AggregationType, BaseTextAggregator
from pipecat.utils.text.simple_text_aggregator import SimpleTextAggregator

from core.pipeline.processors.sentence_splitter import SentenceSplitter


class ChineseTextAggregator(SimpleTextAggregator):
    """
    中文增强的文本聚合器。

    内部委托给 ``SentenceSplitter`` 完成流式切句，具备以下特性：

    - 无需 NLTK lookahead，遇到标点立即切分
    - 首句支持软切分（逗号也可切），降低首音延迟
    - 长度阈值切分，防止超长句子阻塞 TTS 管道
    - 支持波浪号（～ ~）等中文口语句尾标记（已内置于 SentenceSplitter 的硬标点集）
    """

    def __init__(self, force_split_threshold: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        self._splitter = SentenceSplitter(force_split_threshold=force_split_threshold)

    @property
    def text(self) -> Aggregation:
        """返回当前缓冲区内容（尚未切分的部分）。"""
        return Aggregation(
            text=self._splitter.buffer,
            type=AggregationType.SENTENCE,
        )

    async def aggregate(self, text: str) -> AsyncIterator[Aggregation]:
        """
        追加 LLM token 并逐句 yield 完整句子。

        完整替代父类的 NLTK lookahead 逻辑，改用 SentenceSplitter。
        """
        if self._aggregation_type == AggregationType.TOKEN:
            if text:
                yield Aggregation(text=text, type=AggregationType.TOKEN)
            return

        for sentence in self._splitter.push(text):
            yield Aggregation(text=sentence, type=AggregationType.SENTENCE)

    async def flush(self) -> Optional[Aggregation]:
        """
        刷出缓冲区剩余文本（响应结束时调用）。
        """
        if self._aggregation_type == AggregationType.TOKEN:
            return None

        remaining = self._splitter.flush()
        if remaining:
            return Aggregation(text=remaining, type=AggregationType.SENTENCE)
        return None

    async def handle_interruption(self) -> None:
        """用户打断时清空缓冲区并重置首句状态。"""
        self._splitter.reset()
        await super().handle_interruption()

    async def reset(self) -> None:
        """重置聚合器到初始状态。"""
        self._splitter.reset()
        await super().reset()
