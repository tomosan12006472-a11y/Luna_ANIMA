from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SettingsRequest(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)
    mode: str = "current"
    reason: str = "unspecified"
