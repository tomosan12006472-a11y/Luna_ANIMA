from __future__ import annotations

from pydantic import BaseModel


class LoraReviewRequest(BaseModel):
    candidate_id: str
    review_status: str = "hold"
    app_scope: str = "anima"
    note: str = ""


class LoraFavoriteRequest(BaseModel):
    lora_id: str = ""
    relative_path: str = ""
    file_name: str = ""
    display_name: str = ""
    favorite: bool | None = None
