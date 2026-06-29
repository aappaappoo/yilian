"""
VAD 打断策略

可动态切换的用户静音策略：
- vad_interrupt_enabled=True（默认）：用户可在机器人 TTS 播放期间随时插话打断
- vad_interrupt_enabled=False：用户在机器人 TTS 播放期间被静音，TTS 播放完毕后才接受用户语音

通过 DataChannel 消息 set_vad_interrupt 在运行时切换。
"""

from __future__ import annotations

from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame, Frame
from pipecat.turns.user_mute.base_user_mute_strategy import BaseUserMuteStrategy


class VADInterruptMuteStrategy(BaseUserMuteStrategy):
    """
    可动态切换的 VAD 打断静音策略。

    当 vad_interrupt_enabled=False 时，机器人说话期间用户帧（语音/转写）
    会被静音抑制，从而防止用户打断正在播放的 TTS。
    当 vad_interrupt_enabled=True 时，策略始终返回 False（不静音），
    允许用户随时打断。
    """

    def __init__(self, vad_interrupt_enabled: bool = True) -> None:
        super().__init__()
        self._vad_interrupt_enabled = vad_interrupt_enabled
        self._bot_speaking = False

    def set_vad_interrupt_enabled(self, enabled: bool) -> None:
        """运行时切换打断开关。"""
        self._vad_interrupt_enabled = enabled

    @property
    def vad_interrupt_enabled(self) -> bool:
        return self._vad_interrupt_enabled

    async def reset(self) -> None:
        """重置为初始状态。"""
        self._bot_speaking = False

    async def process_frame(self, frame: Frame) -> bool:
        """
        处理每一帧，跟踪机器人说话状态。

        Returns:
            True 表示当前应静音用户（即禁止打断），False 表示允许用户输入。
        """
        await super().process_frame(frame)

        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False

        # 未开启打断时，机器人说话期间静音用户
        if not self._vad_interrupt_enabled and self._bot_speaking:
            return True

        return False
