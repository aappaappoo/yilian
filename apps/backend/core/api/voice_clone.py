"""
声音克隆 API

提供：
- POST /api/voice-clone/{audience_id}/upload  — 上传音频文件
- POST /api/voice-clone/{audience_id}/clone   — 调用阿里云百炼 CosyVoice 克隆声音
- POST /api/voice-clone/{audience_id}/reset   — 重置为 persona.yaml 中的默认声音
- GET  /api/voice-clone/{audience_id}/status  — 查询克隆状态
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, File
from loguru import logger

from core.config import settings
from core.logging_utils import STARTUP
from core.persona.schema import load_persona, PersonaLoadError


def _upload_to_oss(content: bytes, object_key: str) -> str:
    """
    将文件内容上传至阿里云 OSS，返回公网 HTTPS URL。

    若 OSS 未配置（缺少任意必填环境变量），抛出 HTTPException(400)。
    """
    missing = [
        name
        for name, val in [
            ("OSS_ACCESS_KEY_ID", settings.oss_access_key_id),
            ("OSS_ACCESS_KEY_SECRET", settings.oss_access_key_secret),
            ("OSS_BUCKET_NAME", settings.oss_bucket_name),
            ("OSS_ENDPOINT", settings.oss_endpoint),
        ]
        if not val
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                "声音克隆需要将音频上传至阿里云 OSS，但以下配置项未设置: "
                + ", ".join(missing)
                + "。请在 .env 中配置 OSS 参数后重试。"
            ),
        )

    try:
        import oss2  # type: ignore[import]
    except ImportError:
        raise HTTPException(status_code=500, detail="oss2 SDK 未安装，请执行 pip install oss2")

    auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
    bucket = oss2.Bucket(auth, f"https://{settings.oss_endpoint}", settings.oss_bucket_name)
    bucket.put_object(object_key, content)

    encoded_key = quote(object_key, safe="/")
    public_url = f"https://{settings.oss_bucket_name}.{settings.oss_endpoint}/{encoded_key}"
    logger.info(f"[{STARTUP}] | Task=OSS上传 | OSS 上传成功: {object_key} -> {public_url}")
    return public_url

router = APIRouter(prefix="/api/voice-clone", tags=["voice-clone"])

# audiences/ 目录（与 audiences API 保持一致），相对于后端应用根目录。
_AUDIENCES_ROOT = Path(__file__).resolve().parents[2] / "audiences"

# 支持的音频格式
_ALLOWED_AUDIO_EXTENSIONS = {"wav", "mp3", "m4a", "flac", "ogg", "aac", "wma", "amr", "webm"}

# 并发写锁（按 audience_id 隔离）
_write_locks: Dict[str, asyncio.Lock] = {}


def _get_write_lock(audience_id: str) -> asyncio.Lock:
    if audience_id not in _write_locks:
        _write_locks[audience_id] = asyncio.Lock()
    return _write_locks[audience_id]


def _validate_audience_id(audience_id: str) -> None:
    """校验 audience_id 不含路径遍历字符。"""
    if "/" in audience_id or "\\" in audience_id or ".." in audience_id:
        raise HTTPException(status_code=400, detail="非法的 audience_id")


def _safe_audience_dir(audience_id: str) -> Path:
    """
    返回已解析的 audiences/{audience_id} 目录，并校验其在 _AUDIENCES_ROOT 下。
    同时确认该目录真实存在。
    """
    resolved = (_AUDIENCES_ROOT / audience_id).resolve()
    allowed = _AUDIENCES_ROOT.resolve()
    if not resolved.is_relative_to(allowed):
        raise HTTPException(status_code=400, detail="路径越界")
    if not resolved.is_dir():
        raise HTTPException(status_code=404, detail=f"audience '{audience_id}' 不存在")
    return resolved


def _safe_assets_dir(audience_id: str) -> Path:
    """返回已解析的 assets 目录（不要求预先存在）。"""
    audience_dir = _safe_audience_dir(audience_id)
    return audience_dir / "assets"


def _safe_config_path(audience_id: str) -> Path:
    """返回已解析且路径安全的 voice_clone_config.json 路径。"""
    assets_dir = _safe_assets_dir(audience_id).resolve()
    config_path = (assets_dir / "voice_clone_config.json").resolve()
    if not config_path.is_relative_to(assets_dir):
        raise HTTPException(status_code=400, detail="路径越界")
    return config_path


def _load_voice_clone_config(audience_id: str) -> Optional[Dict[str, Any]]:
    config_path = _safe_config_path(audience_id)
    if not config_path.exists():
        return None
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"[{STARTUP}] | Task=声音克隆配置 | 读取 voice_clone_config.json 失败: {exc}")
        return None


def _save_voice_clone_config(audience_id: str, config: Dict[str, Any]) -> None:
    config_path = _safe_config_path(audience_id)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _get_default_voice(audience_id: str) -> str:
    """从 persona.yaml 读取默认声音。"""
    audience_dir = _safe_audience_dir(audience_id)
    persona_path = (audience_dir / "persona.yaml").resolve()
    if not persona_path.is_relative_to(audience_dir):
        return ""
    if not persona_path.exists():
        return ""
    try:
        persona = load_persona(persona_path)
        return persona.voice or ""
    except PersonaLoadError:
        return ""


def get_active_cloned_voice_id(audience_id: str) -> Optional[str]:
    """
    返回当前角色激活的克隆声音 ID，若无则返回 None。

    供 webrtc.py 在建立 TTS Pipeline 时调用，
    确保新会话使用已克隆的声音而非 persona 默认声音。
    """
    cfg = get_active_cloned_voice_config(audience_id)
    return cfg["cloned_voice_id"] if cfg else None


def get_active_cloned_voice_config(audience_id: str) -> Optional[Dict[str, str]]:
    """
    返回当前角色激活的克隆声音配置（voice_id + tts_model），若无则返回 None。

    供 webrtc.py 在建立 TTS Pipeline 时调用，同时覆盖声音和模型，
    确保新会话使用已克隆的声音而非 persona 默认声音。
    """
    # 校验 audience_id 不含路径遍历字符
    if not audience_id or "/" in audience_id or "\\" in audience_id or ".." in audience_id:
        return None
    allowed = _AUDIENCES_ROOT.resolve()
    config_path = (_AUDIENCES_ROOT / audience_id / "assets" / "voice_clone_config.json").resolve()
    # 路径安全：确保解析后的路径仍在 _AUDIENCES_ROOT 内
    if not config_path.is_relative_to(allowed):
        return None
    if not config_path.exists():
        return None
    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        if config.get("is_active") and config.get("cloned_voice_id"):
            return {
                "cloned_voice_id": config["cloned_voice_id"],
                "tts_model": config.get("tts_model", ""),
            }
    except Exception as exc:
        logger.warning(f"[{STARTUP}] | Task=声音克隆配置 | 读取克隆声音配置失败: audience={audience_id}, error={exc}")
    return None


@router.post("/{audience_id}/upload")
async def upload_voice_sample(
    audience_id: str,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """
    上传音频文件到 audiences/{audience_id}/assets/voice_samples/ 目录。

    返回保存后的文件名，供后续克隆 API 使用。
    """
    _validate_audience_id(audience_id)
    assets_dir = _safe_assets_dir(audience_id)

    # 校验文件扩展名
    orig_filename = file.filename or ""
    ext = orig_filename.rsplit(".", 1)[-1].lower() if "." in orig_filename else ""
    if ext not in _ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的音频格式: {ext}，支持: {', '.join(sorted(_ALLOWED_AUDIO_EXTENSIONS))}",
        )

    # 校验文件大小
    max_bytes = settings.voice_clone_max_file_size_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大允许 {settings.voice_clone_max_file_size_mb}MB",
        )

    # 保存到 voice_samples 子目录，使用 UUID 保证唯一性
    samples_dir = (assets_dir / "voice_samples").resolve()
    samples_dir.mkdir(parents=True, exist_ok=True)

    saved_filename = f"voice_sample_{uuid.uuid4().hex}.{ext}"

    # 路径安全校验（防止符号链接等绕过）
    save_path = (samples_dir / saved_filename).resolve()
    if not save_path.is_relative_to(samples_dir):
        raise HTTPException(status_code=400, detail="路径越界")

    with open(save_path, "wb") as f_out:
        f_out.write(content)

    logger.info(f"[{STARTUP}] | Task=音频上传 | 音频上传成功: audience={audience_id}, file={saved_filename}")
    return {"filename": saved_filename, "size": len(content), "status": "uploaded"}


@router.post("/{audience_id}/clone")
async def clone_voice(
    audience_id: str,
    body: Dict[str, Any],
) -> Dict[str, Any]:
    """
    调用阿里云百炼 CosyVoice VoiceEnrollmentService 进行声音复刻。

    请求体：
    {
        "filename": "voice_sample_<uuid>.wav"   // 已上传的文件名
    }
    """
    _validate_audience_id(audience_id)
    assets_dir = _safe_assets_dir(audience_id)

    filename: str = body.get("filename", "")
    if not filename:
        raise HTTPException(status_code=400, detail="缺少 filename 字段")

    # 校验 filename 安全性（不允许路径分隔符或遍历）
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法的文件名")

    samples_dir = (assets_dir / "voice_samples").resolve()
    sample_path = (samples_dir / filename).resolve()
    if not sample_path.is_relative_to(samples_dir):
        raise HTTPException(status_code=400, detail="路径越界")
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail=f"音频文件不存在: {filename}")

    # 读取 persona 中的 tts_model 作为 target_model
    audience_dir = _safe_audience_dir(audience_id)
    persona_path = (audience_dir / "persona.yaml").resolve()
    tts_model = settings.voice_clone_target_model
    if persona_path.is_relative_to(audience_dir) and persona_path.exists():
        try:
            persona = load_persona(persona_path)
            if persona.tts_model:
                tts_model = persona.tts_model
        except PersonaLoadError:
            pass

    # 构建音频文件可访问的 URL
    # 若请求体已提供 audio_url（公网 HTTP/HTTPS），直接使用；
    # 否则读取本地文件并上传到阿里云 OSS 获取公网 URL。
    provided_url: str = body.get("audio_url", "")
    if provided_url:
        audio_file_url = provided_url
    else:
        safe_audience = re.sub(r'[^a-z0-9_-]', '', audience_id.lower()) or "default"
        object_key = (
            settings.oss_voice_clone_prefix.rstrip("/")
            + f"/{safe_audience}/{filename}"
        )
        file_content = sample_path.read_bytes()
        audio_file_url = _upload_to_oss(file_content, object_key)

    # prefix：仅允许数字和小写字母，小于 10 个字符
    safe_prefix = re.sub(r'[^a-z0-9]', '', audience_id.lower())[:8] or "default"

    try:
        api_key = settings.voice_clone_api_key or settings.dashscope_api_key
        import dashscope
        dashscope.api_key = api_key

        from dashscope.audio.tts_v2 import VoiceEnrollmentService  # type: ignore[import]

        service = VoiceEnrollmentService()
        safe_prefix = re.sub(r'[^a-z0-9]', '', audience_id.lower())[:8] or "soulmeet"
        voice_id = service.create_voice(
            target_model=tts_model,
            prefix=safe_prefix,
            url=audio_file_url,
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="dashscope SDK 未安装或版本不支持 VoiceEnrollmentService")
    except Exception as exc:
        logger.error(f"[{STARTUP}] | Task=声音克隆 | 声音克隆失败: audience={audience_id}, error={exc}")
        raise HTTPException(status_code=500, detail=f"声音克隆失败: {exc}")

    config = {
        "cloned_voice_id": voice_id,
        "tts_model": tts_model,
        "source_file": filename,
        "created_at": datetime.now().isoformat(),
        "is_active": True,
    }

    async with _get_write_lock(audience_id):
        _save_voice_clone_config(audience_id, config)

    logger.info(f"[{STARTUP}] | Task=声音克隆 | 克隆成功: audience={audience_id}, voice_id={voice_id}")
    return {"voice_id": voice_id, "status": "success"}


@router.post("/{audience_id}/reset")
async def reset_voice(audience_id: str) -> Dict[str, Any]:
    """
    将 voice_clone_config.json 中的 is_active 设为 false，
    角色恢复使用 persona.yaml 中定义的默认 voice。
    """
    _validate_audience_id(audience_id)
    _safe_audience_dir(audience_id)  # 校验 audience 存在

    default_voice = _get_default_voice(audience_id)

    async with _get_write_lock(audience_id):
        config = _load_voice_clone_config(audience_id)
        if config:
            config["is_active"] = False
            _save_voice_clone_config(audience_id, config)

    logger.info(f"[{STARTUP}] | Task=声音重置 | 重置声音: audience={audience_id}, default_voice={default_voice}")
    return {"default_voice": default_voice, "status": "reset"}


@router.get("/{audience_id}/status")
async def get_voice_clone_status(audience_id: str) -> Dict[str, Any]:
    """
    返回当前角色的声音克隆状态。

    响应体示例：
    {
        "has_cloned_voice": true,
        "is_active": true,
        "cloned_voice_id": "soulmeet_aini_xxxx",
        "source_file": "voice_sample_<uuid>.wav",
        "created_at": "2026-04-20T12:00:00",
        "default_voice": "longanhuan"
    }
    """
    _validate_audience_id(audience_id)
    _safe_audience_dir(audience_id)  # 校验 audience 存在

    default_voice = _get_default_voice(audience_id)
    config = _load_voice_clone_config(audience_id)

    if config:
        return {
            "has_cloned_voice": True,
            "is_active": config.get("is_active", False),
            "cloned_voice_id": config.get("cloned_voice_id", ""),
            "source_file": config.get("source_file", ""),
            "created_at": config.get("created_at", ""),
            "default_voice": default_voice,
        }

    return {
        "has_cloned_voice": False,
        "is_active": False,
        "cloned_voice_id": "",
        "source_file": "",
        "created_at": "",
        "default_voice": default_voice,
    }
