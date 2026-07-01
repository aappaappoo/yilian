"""Speech utility API.

Provides one-shot speech-to-text for push-to-talk text input. This route is
kept separate from the WebRTC realtime pipeline so recording a short message
does not affect TTS playback, VAD interruption, or the live voice channel.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from loguru import logger
from pydantic import BaseModel

from core.config import settings
from core.logging_utils import STT, TTS, USER_INPUT, flatten_content

router = APIRouter(prefix="/api/speech", tags=["speech"])

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MIN_AUDIO_BYTES = 800
DEFAULT_STT_TIMEOUT_SECONDS = 18.0
MAX_TTS_TEXT_CHARS = 6000
DEFAULT_TTS_TIMEOUT_MILLIS = 45000


class SpeechTranscribeResponse(BaseModel):
    text: str


class SpeechSynthesizeRequest(BaseModel):
    text: str


def _is_no_valid_audio_error(result: Any) -> bool:
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


def _transcribe_pcm_sync(
    audio: bytes,
    sample_rate: int,
    timeout_seconds: float,
    request_id: str,
) -> str:
    try:
        import dashscope
        from dashscope.audio.asr import Recognition, RecognitionCallback
    except Exception as exc:  # pragma: no cover - depends on runtime package.
        raise RuntimeError("dashscope SDK 未安装或不可用") from exc

    dashscope.api_key = settings.dashscope_api_key
    complete_event = threading.Event()
    final_texts: list[str] = []
    interim_text = ""
    errors: list[str] = []
    event_count = 0

    class Callback(RecognitionCallback):
        def on_event(self, result):
            nonlocal event_count, interim_text
            sentence = result.get_sentence()
            if not sentence:
                return
            text = str(sentence.get("text") or "").strip()
            if not text:
                return
            is_final = bool(sentence.get("sentence_end", not sentence.get("stash_result", False)))
            event_count += 1
            logger.debug(
                f"[{STT}] | Task=按住说话识别 | request={request_id}, "
                f"event={event_count}, is_final={is_final}, text_len={len(text)}"
            )
            if is_final:
                final_texts.append(text)
            else:
                interim_text = text

        def on_error(self, result):
            if _is_no_valid_audio_error(result):
                logger.warning(
                    f"[{STT}] | Task=按住说话识别 | request={request_id}, "
                    f"DashScope 未检测到有效音频: {result}"
                )
                return
            errors.append(str(result))
            logger.error(
                f"[{STT}] | Task=按住说话识别 | request={request_id}, DashScope 回调错误: {result}"
            )
            complete_event.set()

        def on_complete(self):
            logger.debug(f"[{STT}] | Task=按住说话识别 | request={request_id}, DashScope on_complete")
            complete_event.set()

        def on_close(self):
            logger.debug(f"[{STT}] | Task=按住说话识别 | request={request_id}, DashScope on_close")
            complete_event.set()

    recognition = Recognition(
        model=settings.dashscope_stt_model,
        format="pcm",
        sample_rate=sample_rate,
        callback=Callback(),
    )

    try:
        logger.info(
            f"[{STT}] | Task=按住说话识别 | request={request_id}, "
            f"DashScope 开始识别: model={settings.dashscope_stt_model}, sample_rate={sample_rate}, "
            f"bytes={len(audio)}"
        )
        recognition.start()
        chunk_size = max(3200, int(sample_rate * 2 * 0.1))
        chunk_count = 0
        for offset in range(0, len(audio), chunk_size):
            recognition.send_audio_frame(audio[offset:offset + chunk_size])
            chunk_count += 1
        logger.debug(
            f"[{STT}] | Task=按住说话识别 | request={request_id}, "
            f"音频发送完成: chunks={chunk_count}, chunk_size={chunk_size}"
        )
        recognition.stop()
        completed = complete_event.wait(timeout_seconds)
        if not completed:
            logger.warning(
                f"[{STT}] | Task=按住说话识别 | request={request_id}, "
                f"等待 DashScope 完成超时: timeout={timeout_seconds}s"
            )
    finally:
        if not complete_event.is_set():
            try:
                recognition.stop()
            except Exception:
                pass

    if errors:
        raise RuntimeError(errors[-1])

    text = "".join(final_texts).strip() or interim_text.strip()
    return text


def _synthesize_text_sync(text: str, request_id: str) -> tuple[bytes, str, str]:
    try:
        import dashscope
        from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer
    except Exception as exc:  # pragma: no cover - depends on runtime package.
        raise RuntimeError("dashscope SDK 未安装或不可用") from exc

    dashscope.api_key = settings.dashscope_api_key
    model = (
        getattr(settings, "voice_agent_tts_model", None)
        or settings.dashscope_tts_model
        or "cosyvoice-v3-flash"
    )
    voice = (
        getattr(settings, "voice_agent_tts_voice", None)
        or settings.dashscope_tts_voice
        or "longanhuan"
    )
    synthesizer = SpeechSynthesizer(
        model=model,
        voice=voice,
        format=AudioFormat.WAV_24000HZ_MONO_16BIT,
        volume=80,
        speech_rate=1.0,
        pitch_rate=1.0,
        language_hints=["zh"],
    )
    logger.info(
        f"[{TTS}] | Task=聊天播报合成 | request={request_id}, "
        f"DashScope 开始合成: model={model}, voice={voice}, text_len={len(text)}"
    )
    audio = synthesizer.call(text, timeout_millis=DEFAULT_TTS_TIMEOUT_MILLIS)
    if not audio:
        raise RuntimeError("DashScope TTS returned empty audio")
    return audio, model, voice


@router.post("/synthesize")
async def synthesize_speech(request: SpeechSynthesizeRequest) -> Response:
    """Synthesize text with Aliyun CosyVoice for chat voice broadcast."""
    request_id = uuid4().hex[:8]
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="播报文本不能为空")
    if len(text) > MAX_TTS_TEXT_CHARS:
        raise HTTPException(status_code=413, detail="播报文本太长，请缩短后重试")

    started_at = time.perf_counter()
    try:
        audio, model, voice = await asyncio.to_thread(_synthesize_text_sync, text, request_id)
    except RuntimeError as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.error(
            f"[{TTS}] | Task=聊天播报合成 | request={request_id}, "
            f"DashScope 合成失败: elapsed_ms={elapsed_ms}, error={exc}"
        )
        raise HTTPException(status_code=502, detail="语音播报合成失败，请稍后重试") from exc
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.error(
            f"[{TTS}] | Task=聊天播报合成 | request={request_id}, "
            f"未知错误: elapsed_ms={elapsed_ms}, error={exc}"
        )
        raise HTTPException(status_code=500, detail="语音播报服务异常") from exc

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        f"[{TTS}] | Task=聊天播报合成 | request={request_id}, "
        f"合成完成: elapsed_ms={elapsed_ms}, bytes={len(audio)}, "
        f"model={model}, voice={voice}, text='{flatten_content(text, max_len=80)}'"
    )
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "X-TTS-Model": model,
            "X-TTS-Voice": voice,
        },
    )


@router.post("/transcribe", response_model=SpeechTranscribeResponse)
async def transcribe_speech(
    request: Request,
    audio: UploadFile = File(...),
    sample_rate: int = Form(default=16000),
) -> SpeechTranscribeResponse:
    """Transcribe a short 16-bit mono PCM clip with DashScope Paraformer."""
    request_id = uuid4().hex[:8]
    client_ip = request.client.host if request.client else ""
    logger.info(
        f"[{STT}] | Task=按住说话识别 | request={request_id}, 请求进入: "
        f"client_ip={client_ip or '<空>'}, filename={audio.filename or '<空>'}, "
        f"content_type={audio.content_type or '<空>'}, sample_rate={sample_rate}"
    )

    if sample_rate not in (8000, 16000):
        logger.warning(
            f"[{STT}] | Task=按住说话识别 | request={request_id}, "
            f"不支持的 sample_rate={sample_rate}"
        )
        raise HTTPException(status_code=400, detail="Unsupported sample_rate")

    payload = await audio.read()
    estimated_duration_ms = int(len(payload) / max(1, sample_rate * 2) * 1000)
    logger.info(
        f"[{STT}] | Task=按住说话识别 | request={request_id}, 音频读取完成: "
        f"bytes={len(payload)}, estimated_duration_ms={estimated_duration_ms}"
    )
    if len(payload) < MIN_AUDIO_BYTES:
        logger.warning(
            f"[{STT}] | Task=按住说话识别 | request={request_id}, "
            f"音频过短: bytes={len(payload)}, min={MIN_AUDIO_BYTES}"
        )
        raise HTTPException(status_code=400, detail="录音太短，请按住说完后再松开")
    if len(payload) > MAX_AUDIO_BYTES:
        logger.warning(
            f"[{STT}] | Task=按住说话识别 | request={request_id}, "
            f"音频过长: bytes={len(payload)}, max={MAX_AUDIO_BYTES}"
        )
        raise HTTPException(status_code=413, detail="录音太长，请缩短后重试")

    started_at = time.perf_counter()
    try:
        text = await asyncio.to_thread(
            _transcribe_pcm_sync,
            payload,
            sample_rate,
            DEFAULT_STT_TIMEOUT_SECONDS,
            request_id,
        )
    except RuntimeError as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.error(
            f"[{STT}] | Task=按住说话识别 | request={request_id}, "
            f"DashScope 识别失败: elapsed_ms={elapsed_ms}, error={exc}"
        )
        raise HTTPException(status_code=502, detail="语音识别失败，请稍后重试") from exc
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.error(
            f"[{STT}] | Task=按住说话识别 | request={request_id}, "
            f"未知错误: elapsed_ms={elapsed_ms}, error={exc}"
        )
        raise HTTPException(status_code=500, detail="语音识别服务异常") from exc

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    if not text:
        logger.warning(
            f"[{STT}] | Task=按住说话识别 | request={request_id}, "
            f"识别结果为空: elapsed_ms={elapsed_ms}, audio_bytes={len(payload)}"
        )
        raise HTTPException(status_code=422, detail="没有识别到清晰语音")

    logger.info(
        f"[{USER_INPUT}] | Task=按住说话识别 | request={request_id}, "
        f"识别完成: elapsed_ms={elapsed_ms}, text_len={len(text)}, "
        f"text='{flatten_content(text, max_len=80)}'"
    )
    return SpeechTranscribeResponse(text=text)
