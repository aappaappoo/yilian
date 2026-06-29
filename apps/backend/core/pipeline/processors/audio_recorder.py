"""
音频录制处理器

将用户语音和机器人 TTS 语音保存到 memories/{identity}/{time_bucket}/audio/ 目录。

文件命名：{YYYYMMDDHHММ}-{role}.wav
  - user:        用户语音（InputAudioRawFrame，由 VAD 事件划定边界）
  - {audiences}: 机器人语音（TTSAudioRawFrame，由 TTSStartedFrame/TTSStoppedFrame 划定边界）

使用方式（在 Pipeline 中放置两个实例）：
  transport.input() → [AudioRecorderProcessor(mode="user")] → stt → ...
  ... → tts → [AudioRecorderProcessor(mode="bot")] → transport.output()

两个实例共享同一个 MemoryFileStore 实例，均通过 set_identity() 注入。
"""

from __future__ import annotations
import struct
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameProcessor

from core.logging_utils import MEM_SYS

if TYPE_CHECKING:
    from core.conversation.file_store import MemoryFileStore


class AudioRecorderProcessor(FrameProcessor):
    """
    音频录制处理器。

    拦截音频帧，在对话轮次边界（VAD/TTS 事件）将 PCM 数据保存为 WAV 文件。

    mode="user"：
        放置于 transport.input() 之后、stt 之前。
        拦截 InputAudioRawFrame，使用 UserStartedSpeakingFrame /
        UserStoppedSpeakingFrame 划定每轮用户发言边界。

    mode="bot"：
        放置于 tts 之后、transport.output() 之前。
        拦截 TTSAudioRawFrame，使用 TTSStartedFrame / TTSStoppedFrame
        划定每轮机器人发言边界。

    file_store 和身份信息通过 set_identity() 在 Pipeline 启动后注入。
    未注入 file_store 时处理器透明传递所有帧，不做任何录制。
    """

    def __init__(self, mode: str, sample_rate: int) -> None:
        """
        Args:
            mode:        "user" 或 "bot"
            sample_rate: 音频采样率（Hz）。
                         用户音频通常为 16000，机器人音频通常为 22050。
        """
        super().__init__()
        if mode not in ("user", "bot"):
            raise ValueError(
                f"AudioRecorderProcessor mode 必须是 'user' 或 'bot'，收到: {mode!r}"
            )
        self._mode = mode
        self._sample_rate = sample_rate

        self._file_store: Optional[MemoryFileStore] = None
        self._user_id: str = ""
        self._speaker_id: str = ""
        self._session_id: str = ""
        self._audiences: str = ""

        # PCM 缓冲区（当前轮次）
        self._audio_buffer: List[bytes] = []
        self._recording: bool = False
        self._turn_start_time: Optional[datetime] = None

    def set_identity(
        self,
        file_store: "MemoryFileStore",
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        audiences: str = "",
    ) -> None:
        """注入文件存储和身份标识（在 Pipeline 启动后调用）。"""
        self._file_store = file_store
        self._user_id = user_id
        self._speaker_id = speaker_id
        self._session_id = session_id
        self._audiences = audiences

    async def process_frame(self, frame: Frame, direction) -> None:
        await super().process_frame(frame, direction)

        if self._file_store is not None:
            if self._mode == "user":
                await self._handle_user_frame(frame)
            else:
                await self._handle_bot_frame(frame)

        await self.push_frame(frame, direction)

    # ── 用户音频处理 ──

    async def _handle_user_frame(self, frame: Frame) -> None:
        if isinstance(frame, UserStartedSpeakingFrame):
            self._recording = True
            self._audio_buffer.clear()
            self._turn_start_time = datetime.now()

        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._recording = False
            if self._audio_buffer and self._turn_start_time:
                chunks = self._audio_buffer.copy()
                start = self._turn_start_time
                self._audio_buffer.clear()
                self._turn_start_time = None
                self._schedule_save(chunks, "user", start)

        elif isinstance(frame, InputAudioRawFrame) and self._recording:
            self._audio_buffer.append(frame.audio)

    # ── 机器人音频处理 ──

    async def _handle_bot_frame(self, frame: Frame) -> None:
        if isinstance(frame, TTSStartedFrame):
            self._recording = True
            self._audio_buffer.clear()
            self._turn_start_time = datetime.now()

        elif isinstance(frame, TTSStoppedFrame):
            self._recording = False
            if self._audio_buffer and self._turn_start_time:
                chunks = self._audio_buffer.copy()
                start = self._turn_start_time
                self._audio_buffer.clear()
                self._turn_start_time = None
                role = self._audiences or "assistant"
                self._schedule_save(chunks, role, start)

        elif isinstance(frame, TTSAudioRawFrame) and self._recording:
            self._audio_buffer.append(frame.audio)

    # ── 文件写入调度 ──

    def _schedule_save(
        self,
        chunks: List[bytes],
        role: str,
        start_time: datetime,
    ) -> None:
        """以 fire-and-forget 方式调度音频文件写入（不阻塞对话流）。"""
        pcm_data = b"".join(chunks)
        if not pcm_data or self._file_store is None:
            return

        # 静音检测：如果音频平均音量低于阈值，视为无有效内容，跳过保存 ──
        if self._is_silent(pcm_data):
            logger.debug(
                f"[{MEM_SYS}] | Task=音频录制调度 | "
                f"mode={self._mode}, role={role}, "
                f"跳过：音频内容为静音（无有效音频输入）"
            )
            return

        task = asyncio.create_task(
            self._file_store.save_audio_file(
                user_id=self._user_id,
                speaker_id=self._speaker_id,
                session_id=self._session_id,
                role=role,
                start_time=start_time,
                pcm_data=pcm_data,
                sample_rate=self._sample_rate,
            )
        )
        self._file_store.register_write_task(task)
        logger.debug(
            f"[{MEM_SYS}] | Task=音频录制调度 | "
            f"mode={self._mode}, role={role}, "
            f"大小={len(pcm_data)}字节, 采样率={self._sample_rate}Hz"
        )
    @staticmethod
    def _is_silent(pcm_data: bytes, threshold: int = 500) -> bool:
        """
        检测 PCM 音频是否为静音。

        Args:
            pcm_data:  16-bit mono PCM 字节数据
            threshold: 平均绝对振幅阈值（16-bit 范围 0~32768），
                       低于此值视为静音。默认 500 适用于大多数麦克风噪声。
        Returns:
            True 表示静音，应跳过保存。
        """
        if len(pcm_data) < 2:
            return True
        # 将 PCM bytes 解码为 16-bit signed int 样本
        num_samples = len(pcm_data) // 2
        samples = struct.unpack(f"<{num_samples}h", pcm_data[:num_samples * 2])
        # 计算平均绝对振幅
        avg_amplitude = sum(abs(s) for s in samples) / num_samples
        return avg_amplitude < threshold