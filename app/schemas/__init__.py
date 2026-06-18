from __future__ import annotations

from .auth import LoginRequest
from .catalog import (
    FavoriteRequest,
    OriginalCharacterRequest,
    PositivePromptFavoritePatch,
    PositivePromptFavoriteRequest,
    PromptConverterRequest,
    RecipeRequest,
)
from .generation import (
    DynamicPromptPreviewRequest,
    FaceDetailerPostprocessRequest,
    GenerateRequest,
    HandDetailerPostprocessRequest,
    QueueCancelRequest,
)
from .history import HistoryFlagsRequest, PublicSaveRequest
from .loras import LoraFavoriteRequest, LoraReviewRequest
from .reference import I2IFromHistoryRequest
from .settings import SettingsRequest

__all__ = [
    "DynamicPromptPreviewRequest",
    "FaceDetailerPostprocessRequest",
    "FavoriteRequest",
    "GenerateRequest",
    "HandDetailerPostprocessRequest",
    "HistoryFlagsRequest",
    "I2IFromHistoryRequest",
    "LoginRequest",
    "LoraFavoriteRequest",
    "LoraReviewRequest",
    "OriginalCharacterRequest",
    "PositivePromptFavoritePatch",
    "PositivePromptFavoriteRequest",
    "PromptConverterRequest",
    "PublicSaveRequest",
    "QueueCancelRequest",
    "RecipeRequest",
    "SettingsRequest",
]
