"""Neutral memory storage labels.

This module intentionally does not load domain rules, keyword maps, relation
normalizers, or content-type schemas. The conversation memory path may still
need storage labels for SQL rows, but interpretation belongs to the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


_instance: Optional["KnowledgeRules"] = None


@dataclass(frozen=True)
class MemoryStorageLabels:
    summary_msg_type: str = "summary"
    compress_summary_msg_type: str = "compress_summary"
    default_msg_type: str = "memory"
    default_subject: str = "speaker"
    valid_status: str = "valid"
    invalid_status: str = "invalid"
    max_objects_per_record: int = 20
    default_importance: int = 1


class KnowledgeRules:
    """Compatibility facade for storage labels only."""

    def __init__(self, labels: Optional[MemoryStorageLabels] = None) -> None:
        self._labels = labels or MemoryStorageLabels()

    def reload(self) -> None:
        return None

    @property
    def summary_msg_type(self) -> str:
        return self._labels.summary_msg_type

    @property
    def compress_summary_msg_type(self) -> str:
        return self._labels.compress_summary_msg_type

    @property
    def default_msg_type(self) -> str:
        return self._labels.default_msg_type

    @property
    def default_subject(self) -> str:
        return self._labels.default_subject

    @property
    def valid_status(self) -> str:
        return self._labels.valid_status

    @property
    def invalid_status(self) -> str:
        return self._labels.invalid_status

    @property
    def max_objects_per_record(self) -> int:
        return self._labels.max_objects_per_record

    @property
    def default_importance(self) -> int:
        return self._labels.default_importance


def get_rules() -> KnowledgeRules:
    global _instance
    if _instance is None:
        _instance = KnowledgeRules()
    return _instance
