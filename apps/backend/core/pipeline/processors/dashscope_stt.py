"""
DashScope Paraformer STT Processor

将 DashScope 实时语音识别 API 封装为 Pipecat 标准 STTService。
接收音频帧 (InputAudioRawFrame)，输出转写文本帧 (TranscriptionFrame)。

协议: WebSocket 流式传输
模型: paraformer-realtime-v2（可配置）
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Callable, Coroutine, List, Optional
from pipecat.services.settings import STTSettings

import dashscope
from dashscope.audio.asr import (
    Recognition,
    RecognitionCallback,
    RecognitionResult,
)
from loguru import logger
from core.logging_utils import STARTUP, STT, USER_INPUT, EMOTION

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
    UserMuteStartedFrame,
    UserMuteStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.stt_service import STTService


class DashScopeSTTProcessor(STTService):
    """
    DashScope Paraformer 实时 STT。
    继承 Pipecat STTService，实现音频帧到文本帧的转换。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "paraformer-realtime-v2",
        sample_rate: int = 16000,
        language: str = "zh",
        enable_emotion: bool = True,
    ) -> None:
        """
        Args:
            api_key:        DashScope API Key
            model:          STT 模型名
            sample_rate:    音频采样率 (Hz)
            language:       识别语言
            enable_emotion: 是否开启语音情感识别（默认开启）
        """
        # 将 model 和 language 传给父类 STTSettings
        super().__init__(
            sample_rate=sample_rate,
            settings=STTSettings(model=model, language=language),
            ttfs_p99_latency=1.0,
        )
        self._api_key = api_key
        self._model = model
        self._stt_sample_rate = sample_rate
        self._language = language
        self._enable_emotion = enable_emotion
        self._recognition: Optional[Recognition] = None
        self._transcription_queue: asyncio.Queue = asyncio.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._started = False
        self._muted = False
        self._last_stt_emotion: Optional[str] = None
        self._stt_emotion_callback: Optional[
            Callable[[str, float], Coroutine[Any, Any, None]]
        ] = None

        if not self._api_key:
            raise ValueError("DashScope API key is required.")
        dashscope.api_key = self._api_key

    def set_stt_emotion_callback(
        self,
        callback: Callable[[str, float], Coroutine[Any, Any, None]],
    ) -> None:
        """注册 STT 情感回调。

        当 STT 识别到最终结果携带情感标签时，以 fire-and-forget 方式调用此回调。

        Args:
            callback: async def callback(emotion_type: str, confidence: float) -> None
        """
        self._stt_emotion_callback = callback

    def _create_callback(self) -> RecognitionCallback:
        """创建 DashScope Recognition 回调，将识别结果放入异步队列。"""
        queue = self._transcription_queue
        loop = self._loop
        processor = self

        class Callback(RecognitionCallback):
            def on_open(self):
                pass

            def on_close(self):
                pass

            # 实时识别服务推回来的“识别事件”
            def on_event(self, result: RecognitionResult):
                sentence = result.get_sentence()
                if sentence and "text" in sentence:
                    text = sentence["text"].strip()
                    if not text:
                        return
                    is_final = False
                    # sentence_end 存在时直接使用服务端句尾标记
                    if "sentence_end" in sentence:
                        is_final = bool(sentence["sentence_end"])
                    else:
                        is_final = not sentence.get("stash_result", False)

                    # 提取情感标签（仅在 enable_emotion=True 且 API 返回时有值）
                    emotions: List[dict] = sentence.get("emotions", []) or []

                    # 如果 event loop 存在且运行中，异步将结果 put 到队列中
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            queue.put(
                                {"text": text, "is_final": is_final, "emotions": emotions}
                            ),
                            loop,
                        )

            def on_error(self, result: RecognitionResult):
                if processor._is_no_valid_audio_error(result):
                    logger.warning(
                        f"[{STT}] | Task=识别空音频 | DashScope 未检测到有效音频，已忽略: {result}"
                    )
                    return
                logger.error(f"[{STT}] | Task=识别错误 | 识别错误: {result}")

            def on_complete(self):
                pass

        return Callback()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """
        处理管道帧。

        监听 UserMuteStartedFrame / UserMuteStoppedFrame：
        - UserMuteStartedFrame：关闭音频输入门控（静音），停止向 DashScope 发送音频，
          从而完全阻断语音采集与识别。
        - UserMuteStoppedFrame：重新开启音频输入，恢复语音交互能力。

        当 vad_interrupt_enabled=False 且 TTS 正在播报时，用户聚合器
        会广播 UserMuteStartedFrame；TTS 播报结束后广播 UserMuteStoppedFrame。
        通过在 STT 层响应这两个事件，确保打断功能关闭时音频完全被屏蔽。
        """
        if isinstance(frame, UserMuteStartedFrame):
            self._muted = True
            logger.debug(f"[{STT}] | Task=音频门控 | UserMuteStartedFrame 已接收，STT 音频输入已关闭")
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, UserMuteStoppedFrame):
            self._muted = False
            logger.debug(f"[{STT}] | Task=音频门控 | UserMuteStoppedFrame 已接收，STT 音频输入已恢复")
            await self.push_frame(frame, direction)
            return
        await super().process_frame(frame, direction)

    async def start(self, frame: StartFrame) -> None:
        """
        初始化 WebSocket 连接到 DashScope STT 服务。

        Args:
            frame: Pipecat 启动帧

        Returns:
            None
        """
        await super().start(frame)
        await self._connect()

    async def stop(self, frame: EndFrame) -> None:
        """
        关闭 WebSocket 连接，释放资源。

        Args:
            frame: Pipecat 停止帧

        Returns:
            None
        """
        await super().stop(frame)
        if self._recognition and self._started:
            try:
                self._recognition.stop()
            except Exception as e:
                logger.warning(f"[{STT}] | Task=服务停止 | 停止时出错: {e}")
            self._started = False
            self._recognition = None

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """
        处理音频数据，输出转写结果帧。

        Args:
            audio: PCM 音频字节数据

        Yields:
            TranscriptionFrame:
                - text: str — 识别出的文本
                - user_id: str — 用户标识
                - timestamp: str — 时间戳
                - language: str — 识别语言

        Raises:
            STTConnectionError: WebSocket 连接异常
            STTTimeoutError:    识别超时
        """
        if not self._started:
            await self._connect()

        await self._send_audio_chunk(audio)

        async for frame in self._receive_results():
            yield frame

    async def _connect(self) -> None:
        """
        建立到 DashScope STT WebSocket 的连接（内部方法，由 start() 调用）。

        Returns:
            None

        Raises:
            STTConnectionError: 连接失败
        """
        if self._started:
            return

        self._loop = asyncio.get_event_loop()
        callback = self._create_callback()
        recognition_kwargs: dict = {
            "model": self._model,
            "format": "pcm",
            "sample_rate": self._stt_sample_rate,
            "callback": callback,
        }
        if self._enable_emotion:
            recognition_kwargs["enable_emotion"] = True
        self._recognition = Recognition(**recognition_kwargs)
        self._recognition.start()
        self._started = True
        logger.info(
            f"[{STARTUP}] | Task=STT启动 | STT 已启动: model={self._model}, "
            f"enable_emotion={self._enable_emotion}"
        )

    async def _send_audio_chunk(self, audio: bytes) -> None:
        """
        发送一个音频数据块到 WebSocket。

        Args:
            audio: PCM 音频字节数据块

        Returns:
            None
        """
        if not self._recognition or not self._started:
            return
        try:
            audio_bytes: Optional[bytes] = None
            if isinstance(audio, bytes):
                audio_bytes = audio
            elif hasattr(audio, "tobytes"):
                audio_bytes = audio.tobytes()

            if not audio_bytes or self._is_silent_pcm(audio_bytes):
                return

            self._recognition.send_audio_frame(audio_bytes)
        except Exception as e:
            err_msg = str(e)
            if "Speech recognition has stopped" in err_msg:
                # 识别服务已停止（如超时或连接断开），重置状态并重新连接
                logger.warning(f"[{STT}] | Task=服务重连 | 识别服务已停止，正在重新连接...")
                self._started = False
                self._recognition = None
                try:
                    await self._connect()
                except Exception as reconnect_err:
                    logger.error(f"[{STT}] | Task=服务重连 | 重新连接失败: {reconnect_err}")
            else:
                logger.error(f"[{STT}] | Task=音频发送 | 发送音频异常: {e}")

    @staticmethod
    def _is_silent_pcm(audio: bytes) -> bool:
        """快速过滤空白 PCM 块，避免向 STT 服务提交无效音频。"""
        return not audio.strip(b"\x00")

    @staticmethod
    def _is_no_valid_audio_error(result: RecognitionResult) -> bool:
        """识别 DashScope 对无有效音频的非致命错误。"""
        code = ""
        message = ""

        if isinstance(result, dict):
            code = str(result.get("code") or "")
            message = str(result.get("message") or "")
        else:
            getter = getattr(result, "get", None)
            if callable(getter):
                try:
                    code = str(getter("code") or "")
                    message = str(getter("message") or "")
                except Exception:
                    pass

        result_text = str(result)
        return (
            code == "NO_VALID_AUDIO_ERROR"
            or message == "NO_VALID_AUDIO_ERROR"
            or "NO_VALID_AUDIO_ERROR" in result_text
        )

    async def _receive_results(self) -> AsyncGenerator[TranscriptionFrame, None]:
        """
        从 WebSocket 接收识别结果。

        Yields:
            TranscriptionFrame: 转写结果帧
        """
        while not self._transcription_queue.empty():
            try:
                result = self._transcription_queue.get_nowait()
                text = result["text"]
                is_final = result["is_final"]
                emotions: list = result.get("emotions", [])
                logger.debug(f"[{STT}] | Task=识别结果 | is_final={is_final}, emotions={emotions}, text='{text[:60]}'")
                if is_final:
                    # 从情感列表中选取置信度最高的情感标签
                    if emotions:
                        top = max(emotions, key=lambda e: e.get("confidence", 0.0))
                        self._last_stt_emotion = top.get("type")
                        confidence = top.get("confidence", 0.0)
                        logger.info(
                            f"[{EMOTION}] | Task=STT情感识别 | STT 情感: type={self._last_stt_emotion}, "
                            f"confidence={confidence:.2f}"
                        )
                        if self._stt_emotion_callback is not None:
                            asyncio.create_task(
                                self._fire_stt_emotion(self._last_stt_emotion, confidence)
                            )
                    else:
                        logger.info(f"[{EMOTION}] | Task=STT情感识别 | STT 情感: 未检测到情感数据")
                    logger.info(f"[{USER_INPUT}] | Task=语音识别 | 最后识别结果: {text}")
                    yield TranscriptionFrame(
                        text=text,
                        user_id=self._user_id,
                        timestamp="",
                        language=self._language,
                    )
                else:
                    # logger.debug(f"DashScopeSTT [interim]: {text}")
                    yield InterimTranscriptionFrame(
                        text=text,
                        user_id=self._user_id,
                        timestamp="",
                        language=self._language,
                    )
            except asyncio.QueueEmpty:
                break

    async def _fire_stt_emotion(self, emotion_type: str, confidence: float) -> None:
        """触发 STT 情感回调（异常安全）。"""
        try:
            await self._stt_emotion_callback(emotion_type, confidence)
        except Exception as exc:
            logger.error(f"[{EMOTION}] | Task=STT情感识别 | STT 情感回调异常: {exc}")
