"""Conversation list and message history API."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.auth.dependencies import CurrentUser, get_current_user
from core.conversation.public_artifact import public_artifact
from core.conversation.sql_store import SQLStore

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
_sql_store: Optional[SQLStore] = None


def set_sql_store(sql_store: Optional[SQLStore]) -> None:
    global _sql_store
    _sql_store = sql_store


def _store() -> SQLStore:
    if _sql_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="对话数据库尚未就绪",
        )
    return _sql_store


class ConversationCreateRequest(BaseModel):
    audience: str = Field(default="Aini")
    title: str = Field(default="新对话")
    conversation_id: Optional[str] = None


class ConversationRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)


class ConversationItem(BaseModel):
    conversation_id: str
    user_id: str = ""
    audiences: str
    title: str
    preview: str = ""
    status: str
    last_session_id: str = ""
    message_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class ConversationMessageItem(BaseModel):
    id: str
    conversation_id: str
    session_id: str
    role: str
    content: str
    source: str = ""
    artifact: Optional[dict[str, Any]] = None
    round_id: Optional[int] = None
    created_at: str = ""


class ConversationDetail(BaseModel):
    conversation: ConversationItem
    messages: list[ConversationMessageItem]


@router.get("", response_model=list[ConversationItem])
async def list_conversations(
    audience: str = "Aini",
    limit: int = 50,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ConversationItem]:
    rows = await _store().list_conversations(
        user_id=current_user.user_id,
        audiences=audience,
        limit=max(1, min(limit, 100)),
    )
    return [ConversationItem(**row) for row in rows]


@router.post("", response_model=ConversationItem, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationItem:
    try:
        row = await _store().create_conversation(
            user_id=current_user.user_id,
            audiences=body.audience.strip() or "Aini",
            conversation_id=(body.conversation_id or "").strip(),
            title=body.title.strip() or "新对话",
            status="active",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ConversationItem(**row)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationDetail:
    conversation = await _store().get_conversation(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    messages = await _store().get_conversation_messages(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
    )
    public_messages = []
    for row in messages:
        item = dict(row)
        item["artifact"] = public_artifact(item.get("artifact"))
        public_messages.append(item)
    return ConversationDetail(
        conversation=ConversationItem(**conversation),
        messages=[ConversationMessageItem(**row) for row in public_messages],
    )


@router.patch("/{conversation_id}", response_model=dict[str, bool])
async def rename_conversation(
    conversation_id: str,
    body: ConversationRenameRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, bool]:
    ok = await _store().rename_conversation(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
        title=body.title,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    return {"ok": True}


@router.delete("/{conversation_id}", response_model=dict[str, bool])
async def delete_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, bool]:
    ok = await _store().soft_delete_conversation(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    return {"ok": True}
