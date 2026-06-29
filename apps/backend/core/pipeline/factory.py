"""Pipeline factory for Soulbot realtime voice.

Voice is now:
  Transport.in -> recorder -> STT -> frontend user text -> emotion -> Soul runtime trigger
  and TTS frames -> recorder -> Transport.out.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

from loguru import logger
from pipecat.frames.frames import InterimTranscriptionFrame, TranscriptionFrame, UserStoppedSpeakingFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameProcessor

from core.config import Settings
from core.logging_utils import EMOTION, STARTUP, USER_INPUT
from core.pipeline.processors.audio_recorder import AudioRecorderProcessor
from core.pipeline.processors.dashscope_stt import DashScopeSTTProcessor
from core.pipeline.processors.dashscope_tts import DashScopeTTSProcessor
from core.pipeline.processors.smart_interrupt_gate import SmartInterruptGateProcessor
from core.pipeline.processors.vad_interrupt_strategy import VADInterruptMuteStrategy

if TYPE_CHECKING:
    from core.persona.schema import PersonaConfig

STT_SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = 22050


@dataclass
class PipelineComponents:
    pipeline: Pipeline
    stt_processor: Any
    tts_processor: Any
    emotion_processor: Any
    user_text_forward: Any = None
    soul_companion_processor: Any = None
    user_audio_recorder: Any = None
    bot_audio_recorder: Any = None
    vad_interrupt_strategy: Any = None
    smart_interrupt_gate: Any = None


class UserTextForwardProcessor(FrameProcessor):
    """Forward final/interim STT text to the frontend data channel."""

    def __init__(self) -> None:
        super().__init__()
        self._connection = None
        self._partial_count = 0
        self._last_partial_text = ""

    def set_connection(self, connection: Any) -> None:
        self._connection = connection

    def set_session_ctx(self, session_ctx: Any) -> None:
        del session_ctx

    async def process_frame(self, frame: Any, direction: Any) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame):
            text = str(frame.text or "")
            if text and self._connection is not None:
                try:
                    self._connection.send_app_message({"type": "user_text_partial", "text": text})
                    self._partial_count += 1
                    self._last_partial_text = text
                except Exception as exc:
                    logger.warning(f"[{USER_INPUT}] | Task=实时语音识别 | partial 发送失败: {exc}")
        elif isinstance(frame, TranscriptionFrame):
            text = str(frame.text or "").strip()
            if text and self._connection is not None:
                try:
                    self._connection.send_app_message({"type": "user_text", "text": text})
                except Exception as exc:
                    logger.warning(f"[{USER_INPUT}] | Task=语音识别 | 发送失败: {exc}")
            logger.info(
                f"[{USER_INPUT}] | Task=语音识别 | final定稿: partials={self._partial_count}, "
                f"final='{text[:80]}', last_partial='{self._last_partial_text[:80]}'"
            )
            self._partial_count = 0
            self._last_partial_text = ""
        await self.push_frame(frame, direction)


class EmotionProcessor(FrameProcessor):
    """Detect emotion after user speech is finalized."""

    def __init__(self) -> None:
        super().__init__()
        self._callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None
        self._accumulated_text = ""

    def set_callback(self, callback: Callable[[str], Coroutine[Any, Any, None]]) -> None:
        self._callback = callback

    async def process_frame(self, frame: Any, direction: Any) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and not isinstance(frame, InterimTranscriptionFrame):
            self._accumulated_text += str(frame.text or "")
        if isinstance(frame, UserStoppedSpeakingFrame):
            text = self._accumulated_text.strip()
            self._accumulated_text = ""
            if text and self._callback is not None:
                try:
                    await self._callback(text)
                except Exception as exc:
                    logger.error(f"[{EMOTION}] | Task=情绪检测 | 回调异常: {exc}")
        await self.push_frame(frame, direction)


class SoulCompanionProcessor(FrameProcessor):
    """Consume final user text and delegate to the Soul companion runtime."""

    def __init__(self) -> None:
        super().__init__()
        self._callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None

    def set_callback(self, callback: Callable[[str], Coroutine[Any, Any, None]]) -> None:
        self._callback = callback

    async def process_frame(self, frame: Any, direction: Any) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and not isinstance(frame, InterimTranscriptionFrame):
            text = str(frame.text or "").strip()
            if text and self._callback is not None:
                await self._callback(text)
            return
        await self.push_frame(frame, direction)


async def build_pipeline(
    transport: Any,
    settings: Settings,
    persona: Optional["PersonaConfig"] = None,
    system_prompt: str = "",
) -> PipelineComponents:
    del system_prompt
    stt = None
    if settings.stt_enabled:
        stt = DashScopeSTTProcessor(
            api_key=settings.dashscope_api_key,
            model=settings.dashscope_stt_model,
            sample_rate=STT_SAMPLE_RATE,
            language="zh",
        )

    tts_voice = settings.dashscope_tts_voice
    tts_model = settings.dashscope_tts_model
    if persona is not None:
        tts_voice = getattr(persona, "voice", None) or tts_voice
        tts_model = getattr(persona, "tts_model", None) or tts_model

    if hasattr(settings, "audience") and settings.audience:
        cfg_path = Path(__file__).resolve().parents[2] / "audiences" / settings.audience / "assets" / "voice_clone_config.json"
        try:
            if cfg_path.exists():
                import json

                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                if cfg.get("is_active") and cfg.get("cloned_voice_id"):
                    tts_voice = cfg["cloned_voice_id"]
        except Exception as exc:
            logger.warning(f"[{STARTUP}] | Task=TTS初始化 | 读取 voice_clone_config.json 失败: {exc}")

    tts = DashScopeTTSProcessor(
        api_key=settings.dashscope_api_key,
        model=tts_model,
        voice=tts_voice,
        sample_rate=TTS_SAMPLE_RATE,
        pool_size=3,
        language="zh",
    )

    user_audio_recorder = AudioRecorderProcessor(mode="user", sample_rate=STT_SAMPLE_RATE)
    bot_audio_recorder = AudioRecorderProcessor(mode="bot", sample_rate=TTS_SAMPLE_RATE)
    user_text_forward = UserTextForwardProcessor()
    emotion_processor = EmotionProcessor()
    soul_companion_processor = SoulCompanionProcessor()
    vad_interrupt_strategy = VADInterruptMuteStrategy(vad_interrupt_enabled=True)
    smart_interrupt_gate = SmartInterruptGateProcessor(interrupt_enabled=True)

    processors = [transport.input(), user_audio_recorder]
    if stt is not None:
        processors.append(stt)
    processors.extend([
        smart_interrupt_gate,
        user_text_forward,
        emotion_processor,
        soul_companion_processor,
        tts,
        bot_audio_recorder,
        transport.output(),
    ])
    pipeline = Pipeline(processors)
    logger.info(
        f"[{STARTUP}] Soul voice pipeline ready: "
        f"STT={settings.dashscope_stt_model}, TTS={tts_model}/{tts_voice}"
    )
    return PipelineComponents(
        pipeline=pipeline,
        stt_processor=stt,
        tts_processor=tts,
        emotion_processor=emotion_processor,
        user_text_forward=user_text_forward,
        soul_companion_processor=soul_companion_processor,
        user_audio_recorder=user_audio_recorder,
        bot_audio_recorder=bot_audio_recorder,
        vad_interrupt_strategy=vad_interrupt_strategy,
        smart_interrupt_gate=smart_interrupt_gate,
    )
