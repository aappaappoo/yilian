import asyncio
import os
import re
import threading
from typing import AsyncGenerator, Optional

# DashScope TTS WebSocket 连接优化：
# - 强制 IPv4：避免 IPv6 解析/连接尝试浪费时间
# - 超时 30s：国内网络 WebSocket 握手通常需要 6~10s，默认 5s 必然超时
os.environ["DASHSCOPE_PREFER_IPV4"] = "true"
os.environ["DASHSCOPE_WS_CONNECTION_TIMEOUT"] = "30"

import dashscope
from dashscope.audio.tts_v2 import (
    AudioFormat,
    SpeechSynthesizer,
    SpeechSynthesizerObjectPool,
    ResultCallback,
)
from pipecat.frames.frames import TTSStoppedFrame, ErrorFrame, TTSAudioRawFrame, Frame, TTSStartedFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from loguru import logger
from core.logging_utils import STARTUP, TTS

# 采样率到 AudioFormat 的映射
_SAMPLE_RATE_FORMAT_MAP = {
    8000: AudioFormat.PCM_8000HZ_MONO_16BIT,
    16000: AudioFormat.PCM_16000HZ_MONO_16BIT,
    22050: AudioFormat.PCM_22050HZ_MONO_16BIT,
    24000: AudioFormat.PCM_24000HZ_MONO_16BIT,
    44100: AudioFormat.PCM_44100HZ_MONO_16BIT,
    48000: AudioFormat.PCM_48000HZ_MONO_16BIT,
}

# Unicode emoji 匹配模式（覆盖 Emoji_Presentation / Emoji_Component 等主要区段）
_EMOJI_PATTERN = re.compile(
    "["
    "\U0000200d"             # Zero Width Joiner
    "\U0000FE00-\U0000FE0F"  # Variation Selectors (incl. VS-16 emoji presentation)
    "\U0000231A-\U0000231B"  # Watch, Hourglass
    "\U000023E9-\U000023F3"  # Various clocks/play buttons
    "\U000023F8-\U000023FA"  # Pause/stop/record
    "\U000025AA-\U000025AB"  # Small squares
    "\U000025B6"             # Play button
    "\U000025C0"             # Reverse button
    "\U000025FB-\U000025FE"  # Medium squares
    "\U00002600-\U000027BF"  # Misc Symbols + Dingbats
    "\U00002934-\U00002935"  # Arrows
    "\U00003030"             # Wavy dash
    "\U0000303D"             # Part alternation mark
    "\U00003297"             # Circled Ideograph Congratulation
    "\U00003299"             # Circled Ideograph Secret
    "\U0000E000-\U0000F8FF"  # Private Use Area (some emoji fonts)
    "\U0001F300-\U0001F9FF"  # Misc Symbols & Pictographs … Supplemental Symbols
    "\U0001FA00-\U0001FA6F"  # Chess symbols
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    """移除文本中的 emoji 字符，防止 TTS 引擎报错。"""
    return _EMOJI_PATTERN.sub("", text)


def _is_tts_websocket_close(message: str) -> bool:
    """DashScope TTS 正常关闭 WebSocket 时也会走 on_error 回调。"""
    normalized = str(message or "").lower()
    return (
        "websocket closed" in normalized
        or " opcode=8 " in f" {normalized} "
        or " - goodbye" in normalized
    )


def _is_tts_no_valid_audio_error(message: str) -> bool:
    """DashScope 在无可合成音频时返回的可恢复错误。"""
    return "no_valid_audio_error" in str(message or "").lower()

# ── 模块级对象池（整个进程共享，预热连接） ──
_TTS_POOL: Optional[SpeechSynthesizerObjectPool] = None

def _get_tts_pool(max_size: int = 3) -> SpeechSynthesizerObjectPool:
    """懒初始化全局 TTS 对象池。"""
    global _TTS_POOL
    if _TTS_POOL is None:
        _TTS_POOL = SpeechSynthesizerObjectPool(max_size=max_size)
    return _TTS_POOL

def _is_v3_model(model: str) -> bool:
    """判断 model 是否为 cosyvoice-v3 系列。"""
    return "v3" in model.lower()


class DashScopeTTSProcessor(TTSService):
    """
    DashScope CosyVoice 流式 TTS（对象池版）。
    """

    def __init__(self, api_key, model="cosyvoice-v2", voice="longxiaochun_v2",
                 sample_rate=24000, pool_size=3, **kwargs):
        super().__init__(
            sample_rate=sample_rate,
            settings=TTSSettings(model=model, voice=voice, language="zh"),
            **kwargs,
        )
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self._tts_sample_rate = sample_rate
        self._speed: float = 1.0
        self._pool_size = pool_size

        self._audio_queue: Optional[asyncio.Queue] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._voice_enabled: bool = True
        self._generation_id: int = 0
        self._emotion: Optional[str] = None

        if not self._api_key:
            raise ValueError("DashScope API key is required.")
        dashscope.api_key = self._api_key
        self._use_pool = not _is_v3_model(model)
        if self._use_pool:
            self._pool = _get_tts_pool(max_size=pool_size)
        else:
            self._pool = None

        logger.info(
            f"[{STARTUP}] | Task=TTS初始化 | TTS 初始化: model={model}, voice={voice}, "
            f"pool_size={pool_size}, use_pool={self._use_pool}"
        )

    def can_generate_metrics(self) -> bool:
        return True

    def set_voice(self, voice: str) -> None:
        self._voice = voice

    def set_model(self, model: str) -> None:
        """动态切换 TTS 模型（如 cosyvoice-v2 → cosyvoice-v3-flash）。"""
        self._model = model
        self._use_pool = not _is_v3_model(model)
        if self._use_pool and self._pool is None:
            self._pool = _get_tts_pool(max_size=self._pool_size)

    def set_speed(self, speed: float) -> None:
        self._speed = max(0.5, min(2.0, speed))

    def set_emotion(self, emotion: Optional[str]) -> None:
        """设置情感参数，用于下一次 TTS 合成时的情感语音控制。

        Args:
            emotion: 情感标签，如 'happy'、'sad'、'angry' 等；传 None 则清除情感。
        """
        self._emotion = emotion
        logger.info(f"[{TTS}] | Task=情感设置 | 情感已设置: {emotion}")

    def set_voice_enabled(self, enabled: bool) -> None:
        """启用或禁用语音合成输出。禁用时 run_tts 直接跳过，仅返回文本回复。"""
        self._voice_enabled = enabled
        logger.info(f"[{TTS}] | Task=语音回复控制 | 语音回复已{'开启' if enabled else '关闭'}")

    def cancel_synthesis(self) -> None:
        """取消当前正在进行的 TTS 合成。

        递增 generation_id 使旧回调丢弃数据，并向当前 queue 注入 None 哨兵
        让 run_tts 的 while 循环立即退出。线程安全（仅操作 int 递增和 queue.put_nowait）。
        """
        self._generation_id += 1
        if self._audio_queue is not None:
            try:
                self._audio_queue.put_nowait(None)
            except Exception:
                pass
        logger.debug(f"[{TTS}] | Task=合成取消 | cancel_synthesis 已触发，generation_id={self._generation_id}")

    def _get_audio_format(self):
        """根据采样率返回对应的 AudioFormat 枚举。"""
        return _SAMPLE_RATE_FORMAT_MAP.get(
            self._tts_sample_rate, AudioFormat.PCM_16000HZ_MONO_16BIT
        )

    def _create_callback(self, gen_id: int):
        """创建 TTS 回调，将音频数据路由到当前的 audio_queue。

        gen_id 为本次合成轮次标识，回调内部写入 queue 前先校验，
        若 generation_id 已推进（说明本轮已被新请求取代）则丢弃数据。
        """
        processor = self

        class TTSCallback(ResultCallback):
            def on_open(self):
                pass

            def on_data(self, data: bytes) -> None:
                if processor._generation_id != gen_id:
                    return
                if data and processor._audio_queue and processor._loop:
                    asyncio.run_coroutine_threadsafe(
                        processor._audio_queue.put(data), processor._loop
                    )

            def on_complete(self):
                if processor._generation_id != gen_id:
                    return
                if processor._audio_queue and processor._loop:
                    asyncio.run_coroutine_threadsafe(
                        processor._audio_queue.put(None), processor._loop
                    )

            def on_error(self, message: str):
                if _is_tts_websocket_close(message):
                    logger.warning(f"[{TTS}] | Task=语音合成 | WebSocket已关闭: {message}")
                elif _is_tts_no_valid_audio_error(message):
                    logger.warning(f"[{TTS}] | Task=语音合成 | 未生成有效音频，已跳过: {message}")
                else:
                    logger.error(f"[{TTS}] | Task=语音合成 | 合成错误: {message}")
                if processor._generation_id != gen_id:
                    return
                if processor._audio_queue and processor._loop:
                    asyncio.run_coroutine_threadsafe(
                        processor._audio_queue.put(None), processor._loop
                    )

            def on_close(self):
                pass

        return TTSCallback()

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        """将文本转为音频帧流（对象池版）。"""

        if not self._voice_enabled:
            logger.debug(f"[{TTS}] | Task=语音合成 | 语音回复已关闭，跳过合成")
            return

        # ── 文本预处理：替换可能导致 TTS API 报错的特殊字符 ──
        text = _strip_emoji(text)
        text = text.replace("...", "…")
        text = text.strip()
        if not text:
            logger.warning(f"[{TTS}] | Task=语音合成 | 文本为空，跳过合成")
            return

        self._generation_id += 1
        current_gen_id = self._generation_id

        # 如果有上一次合成的 queue，注入哨兵让旧 while 循环立即退出
        if self._audio_queue is not None:
            try:
                self._audio_queue.put_nowait(None)
            except Exception:
                pass

        self._audio_queue = asyncio.Queue()
        self._loop = asyncio.get_event_loop()

        try:
            await self.start_ttfb_metrics()
            await self.start_tts_usage_metrics(text)
            yield TTSStartedFrame(context_id=context_id)

            def _run_synthesis():
                synthesizer = None
                current_emotion = self._emotion
                try:
                    callback = self._create_callback(current_gen_id)
                    if self._use_pool and self._pool is not None:
                        logger.info(
                            f"[{TTS}] | Task=语音合成 | 开始合成: model={self._model}, "
                            f"voice={self._voice}, emotion=无(对象池模式)"
                        )
                        synthesizer = self._pool.borrow_synthesizer(
                            model=self._model,
                            voice=self._voice,
                            format=self._get_audio_format(),
                            callback=callback,
                        )
                    else:
                        logger.info(
                            f"[{TTS}] | Task=语音合成 | 开始合成: model={self._model}, "
                            f"voice={self._voice}, emotion={current_emotion or '无'}"
                        )
                        synth_kwargs: dict = {
                            "model": self._model,
                            "voice": self._voice,
                            "format": self._get_audio_format(),
                            "callback": callback,
                        }
                        if current_emotion:
                            synth_kwargs["emotion"] = current_emotion
                        synthesizer = SpeechSynthesizer(**synth_kwargs)

                    synthesizer.streaming_call(text)
                    synthesizer.streaming_complete()
                except Exception as e:
                    if _is_tts_websocket_close(str(e)):
                        logger.warning(f"[{TTS}] | Task=语音合成 | WebSocket已关闭: {e}")
                    elif _is_tts_no_valid_audio_error(str(e)):
                        logger.warning(f"[{TTS}] | Task=语音合成 | 未生成有效音频，已跳过: {e}")
                    else:
                        logger.error(f"[{TTS}] | Task=语音合成 | 合成异常: {e}")
                    if self._generation_id == current_gen_id and self._audio_queue and self._loop:
                        asyncio.run_coroutine_threadsafe(
                            self._audio_queue.put(None), self._loop
                        )
                finally:
                    if synthesizer is not None and self._use_pool and self._pool is not None:
                        try:
                            self._pool.return_synthesizer(synthesizer)
                        except Exception as e:
                            logger.warning(f"[{TTS}] | Task=对象池管理 | 归还合成器失败: {e}")

            synthesis_thread = threading.Thread(target=_run_synthesis, daemon=True)
            synthesis_thread.start()

            first_chunk = True
            while True:
                if self._generation_id != current_gen_id:
                    break
                try:
                    chunk = await asyncio.wait_for(
                        self._audio_queue.get(), timeout=30.0
                    )
                except asyncio.TimeoutError:
                    break
                if chunk is None:
                    break
                # 再次检查 generation_id：防止 cancel 前已入队的旧 chunk 被错误 yield
                # （场景：queue=[stale_chunk, None] 时 cancel 将 gen_id 推进，
                #   stale_chunk 是 non-None，若不检查会继续 yield 旧音频）
                if self._generation_id != current_gen_id:
                    break
                if first_chunk:
                    await self.stop_ttfb_metrics()
                    first_chunk = False
                yield TTSAudioRawFrame(
                    audio=chunk,
                    sample_rate=self._tts_sample_rate,
                    num_channels=1,
                    context_id=context_id,
                )
            yield TTSStoppedFrame(context_id=context_id)
        except Exception as e:
            logger.error(f"[{TTS}] | Task=语音合成 | 处理异常: {e}")
            yield ErrorFrame(error=f"DashScope TTS error: {e}")
        finally:
            await self.stop_ttfb_metrics()
