from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PublicSaveRequest(BaseModel):
    apply_watermark: bool = False
    watermark: dict[str, Any] = Field(default_factory=dict)
    watermark_client: str = ""
    async_save: bool = False


class HistoryFlagsRequest(BaseModel):
    favorite: bool | None = None
    post_candidate: bool | None = None
    hidden: bool | None = None
    tags: list[str] | None = None
    patch: dict[str, Any] = Field(default_factory=dict)
