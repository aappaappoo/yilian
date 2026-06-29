"""
人物发现 API

提供：
- GET /api/audiences                          — 返回所有已注册 audience 的列表（含名称、描述、头像 URL）
- GET /api/audiences/{name}/assets/{filename} — 静态资源代理（从 audiences/{name}/assets/ 提供文件）
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from loguru import logger

from core.logging_utils import STARTUP
from core.persona.schema import load_persona, PersonaLoadError

router = APIRouter(prefix="/api/audiences", tags=["audiences"])

# audiences/ 目录相对于后端应用根目录，避免受启动 cwd 影响。
_AUDIENCES_ROOT = Path(__file__).resolve().parents[2] / "audiences"


class AudienceInfo(BaseModel):
    """单个 audience 的元信息，用于前端卡片渲染。"""
    id: str
    name: str
    description: str
    avatar_url: str
    vrm_url: str


def _discover_audiences() -> List[AudienceInfo]:
    """扫描 audiences/ 目录，收集所有包含 persona.yaml 的子目录并读取人设信息。"""
    result: List[AudienceInfo] = []
    if not _AUDIENCES_ROOT.is_dir():
        logger.warning(f"[{STARTUP}] | Task=人设发现 | [audiences API] audiences/ 目录不存在: {_AUDIENCES_ROOT.resolve()}")
        return result

    for sub in sorted(_AUDIENCES_ROOT.iterdir()):
        if not sub.is_dir():
            continue
        if not (sub / "persona.yaml").exists():
            continue

        audience_id = sub.name
        persona_path = sub / "persona.yaml"

        try:
            persona = load_persona(persona_path) if persona_path.exists() else None
        except PersonaLoadError as exc:
            logger.warning(f"[{STARTUP}] | Task=人设发现 | [audiences API] 跳过 {audience_id}，无法加载人设: {exc}")
            continue

        name = persona.name if persona else audience_id
        description = persona.description if persona else ""
        avatar_image = persona.avatar_image if persona else ""
        vrm_model = persona.vrm_model if persona else ""

        avatar_url = (
            f"/api/audiences/{audience_id}/assets/{avatar_image}"
            if avatar_image
            else ""
        )
        vrm_url = (
            f"/api/audiences/{audience_id}/assets/{vrm_model}"
            if vrm_model
            else ""
        )

        result.append(AudienceInfo(
            id=audience_id,
            name=name,
            description=description,
            avatar_url=avatar_url,
            vrm_url=vrm_url,
        ))

    logger.info(f"[{STARTUP}] | Task=人设发现 | [audiences API] 共发现 {len(result)} 个 audience")
    return result


@router.get("", response_model=List[AudienceInfo])
async def list_audiences() -> List[AudienceInfo]:
    """返回所有已注册 audience 的元信息列表。"""
    return _discover_audiences()


@router.get("/{name}/assets/{filename}")
async def get_audience_asset(name: str, filename: str) -> FileResponse:
    """
    从 audiences/{name}/assets/{filename} 返回静态资源文件。

    带路径安全校验，防止路径遍历攻击（如 ../../etc/passwd）。
    """
    # 安全校验：name 和 filename 不能包含路径分隔符
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="非法的 audience 名称")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法的文件名")

    asset_path = (_AUDIENCES_ROOT / name / "assets" / filename).resolve()
    # 再次校验解析后路径在允许范围内（防止符号链接等绕过）
    allowed_root = (_AUDIENCES_ROOT / name / "assets").resolve()
    if not asset_path.is_relative_to(allowed_root):
        raise HTTPException(status_code=400, detail="路径越界")

    if not asset_path.exists():
        raise HTTPException(status_code=404, detail=f"资源文件不存在: {filename}")

    media_type = "model/gltf-binary" if asset_path.suffix.lower() == ".vrm" else None
    headers = {"Cache-Control": "public, max-age=86400"} if media_type else None
    return FileResponse(str(asset_path), media_type=media_type, headers=headers)


@router.get("/{name}/background/{filename}")
async def get_audience_background(name: str, filename: str):
    """
    从 audiences/{name}/background/{filename} 返回背景资源文件。
    """
    base_dir = (_AUDIENCES_ROOT / name / "background").resolve()
    file_path = (base_dir / filename).resolve()

    if not str(file_path).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="invalid filename")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="background file not found")

    return FileResponse(file_path)
