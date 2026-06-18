from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=32)
