"""Smart interruption gate for realtime voice input."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Awaitable, Callable, Optional

from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from core.logging_utils import USER_INPUT

InterruptCallback = Callable[[str, str], Awaitable[None]]

_CONTROL_PHRASES = (
    "等等",
    "等一下",
    "等下",
    "停一下",
    "暂停",
    "停止",
    "停",
    "别说",
    "先别",
    "打断",
    "不对",
    "不是",
    "错了",
    "取消",
    "换个",
    "重新",
    "我想问",
    "我问",
    "先回答",
    "听我说",
)

_BACKCHANNELS = {
    "嗯",
    "嗯嗯",
    "啊",
    "哦",
    "噢",
    "喔",
    "呃",
    "额",
    "唔",
    "好",
    "好的",
    "好啊",
    "好吧",
    "行",
    "可以",
    "知道",
    "知道了",
    "明白",
    "明白了",
    "了解",
    "对",
    "是",
    "是的",
    "没错",
    "继续",
    "谢谢",
    "ok",
    "okay",
    "yes",
    "yeah",
    "uhhuh",
    "uh-huh",
}

_QUERY_MARKERS = (
    "吗",
    "呢",
    "怎么",
    "为什么",
    "哪里",
    "哪儿",
    "几点",
    "多少",
    "谁",
    "能不能",
    "可不可以",
)

_PUNCT_RE = re.compile(r"[\s，。！？、,.!?;:：；\"'“”‘’（）()【】\[\]{}<>《》…~·`|/\\_-]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class VoiceInterruptDecision:
    should_forward: bool
    should_interrupt: bool
    reason: str


def _normalize_text(text: str) -> str:
    return _PUNCT_RE.sub("", text.lower()).strip()


def _count_cjk(text: str) -> int:
    return len(_CJK_RE.findall(text))


def _count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _is_backchannel(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return True
    if normalized in _BACKCHANNELS:
        return True
    return bool(re.fullmatch(r"(嗯+|啊+|哦+|噢+|喔+|呃+|额+|唔+|好+|对+|是+|ok+|yes+|yeah+)", normalized))


def _looks_like_bot_echo(user_text: str, bot_text: str) -> bool:
    user_norm = _normalize_text(user_text)
    bot_norm = _normalize_text(bot_text)
    if len(user_norm) < 4 or len(bot_norm) < 8:
        return False
    if user_norm in bot_norm:
        return True
    if len(user_norm) < 8:
        return False
    if SequenceMatcher(None, user_norm, bot_norm).ratio() >= 0.82:
        return True
    overlap = sum(1 for ch in user_norm if ch in bot_norm)
    return overlap / max(len(user_norm), 1) >= 0.86


def _is_explicit_control(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(phrase in normalized for phrase in _CONTROL_PHRASES)


def _is_substantive_turn(text: str) -> bool:
    normalized = _normalize_text(text)
    cjk_count = _count_cjk(normalized)
    word_count = _count_words(normalized)
    if cjk_count >= 6 or word_count >= 3:
        return True
    if cjk_count >= 2 and any(marker in normalized for marker in _QUERY_MARKERS):
        return True
    return False


def classify_voice_interrupt(
    *,
    text: str,
    bot_text: str,
    bot_speaking: bool,
    interrupt_enabled: bool,
) -> VoiceInterruptDecision:
    """Classify whether a transcription should interrupt bot speech."""

    clean_text = text.strip()
    if not clean_text:
        return VoiceInterruptDecision(False, False, "empty")
    if not bot_speaking:
        return VoiceInterruptDecision(True, False, "normal_user_turn")
    if not interrupt_enabled:
        return VoiceInterruptDecision(False, False, "disabled_during_bot_speech")
    if _looks_like_bot_echo(clean_text, bot_text):
        return VoiceInterruptDecision(False, False, "bot_echo")
    if _is_explicit_control(clean_text):
        return VoiceInterruptDecision(True, True, "explicit_control")
    if _is_backchannel(clean_text):
        return VoiceInterruptDecision(False, False, "backchannel")
    if _is_substantive_turn(clean_text):
        return VoiceInterruptDecision(True, True, "substantive_turn")
    return VoiceInterruptDecision(False, False, "too_short")


class SmartInterruptGateProcessor(FrameProcessor):
    """Filter realtime STT while the bot is speaking and trigger real barge-in."""

    def __init__(self, interrupt_enabled: bool = True) -> None:
        super().__init__()
        self._interrupt_enabled = interrupt_enabled
        self._bot_speaking = False
        self._current_bot_text = ""
        self._interrupt_fired = False
        self._bot_state_expires_at = 0.0
        self._interrupt_callback: Optional[InterruptCallback] = None

    @property
    def interrupt_enabled(self) -> bool:
        return self._interrupt_enabled

    def set_interrupt_enabled(self, enabled: bool) -> None:
        self._interrupt_enabled = enabled

    def set_interrupt_callback(self, callback: InterruptCallback) -> None:
        self._interrupt_callback = callback

    async def _trigger_interrupt(self, reason: str, text: str) -> None:
        if self._interrupt_fired:
            return
        self._interrupt_fired = True
        logger.info(
            f"[{USER_INPUT}] | Task=智能语音打断 | 触发打断: reason={reason}, text='{text[:80]}'"
        )
        if self._interrupt_callback is not None:
            await self._interrupt_callback(reason, text)

    def _track_bot_frame(self, frame: Frame) -> None:
        if isinstance(frame, TTSSpeakFrame):
            self._current_bot_text = str(frame.text or "")
            self._bot_speaking = True
            self._interrupt_fired = False
            self._bot_state_expires_at = time.monotonic() + 90.0
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            self._bot_state_expires_at = time.monotonic() + 300.0
        elif isinstance(frame, (BotStoppedSpeakingFrame, InterruptionFrame)):
            self._bot_speaking = False
            self._current_bot_text = ""
            self._interrupt_fired = False
            self._bot_state_expires_at = 0.0

    def _is_bot_active(self) -> bool:
        if not self._bot_speaking:
            return False
        if self._bot_state_expires_at and time.monotonic() > self._bot_state_expires_at:
            self._bot_speaking = False
            self._current_bot_text = ""
            self._interrupt_fired = False
            self._bot_state_expires_at = 0.0
            return False
        return True

    async def _handle_transcription(self, frame: TranscriptionFrame, direction: FrameDirection) -> None:
        text = str(frame.text or "").strip()
        decision = classify_voice_interrupt(
            text=text,
            bot_text=self._current_bot_text,
            bot_speaking=self._is_bot_active(),
            interrupt_enabled=self._interrupt_enabled,
        )

        is_interim = isinstance(frame, InterimTranscriptionFrame)
        if (
            decision.should_interrupt
            and (not is_interim or decision.reason == "explicit_control")
        ):
            await self._trigger_interrupt(decision.reason, text)

        if decision.should_forward:
            await self.push_frame(frame, direction)
            return

        if text and (not is_interim or decision.reason in {"bot_echo", "disabled_during_bot_speech"}):
            logger.info(
                f"[{USER_INPUT}] | Task=智能语音打断 | 抑制语音输入: "
                f"reason={decision.reason}, text='{text[:80]}'"
            )

    async def process_frame(self, frame: Any, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        self._track_bot_frame(frame)

        if isinstance(frame, TranscriptionFrame):
            await self._handle_transcription(frame, direction)
            return

        await self.push_frame(frame, direction)
