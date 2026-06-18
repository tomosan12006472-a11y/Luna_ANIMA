from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PromptConverterRequest(BaseModel):
    source_text: str = Field("", max_length=4000)
    mode: str = "tags"
    existing_positive: str = Field("", max_length=8000)


class FavoriteRequest(BaseModel):
    source: str
    id: str = ""
    name: str = ""
    display_name: str = ""
    prompt_tag: str = ""
    note: str = ""
    tags: list[str] = Field(default_factory=list)


class PositivePromptFavoriteRequest(BaseModel):
    title: str = ""
    prompt: str = ""
    tags: Any = Field(default_factory=list)
    note: str = ""


class PositivePromptFavoritePatch(BaseModel):
    title: str | None = None
    prompt: str | None = None
    tags: Any = None
    note: str | None = None
    favorite: bool | None = None


class RecipeRequest(BaseModel):
    name: str = ""
    summary: str = ""
    request: dict[str, Any] = Field(default_factory=dict)


class OriginalCharacterRequest(BaseModel):
    id: str = ""
    display_name: str = ""
    trigger_words: list[str] = Field(default_factory=list)
    positive_tags: list[str] = Field(default_factory=list)
    identity_prompt: str = ""
    negative_guard: str = ""
    default_lora: str | None = None
    favorite: bool = False
