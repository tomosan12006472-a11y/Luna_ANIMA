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
    DynamicPromptSettings,
    FaceDetailerPostprocessRequest,
    FaceDetailerRequestSettings,
    GenerateRequest,
    HandDetailerRequestSettings,
    HandDetailerPostprocessRequest,
    HiresFixSettings,
    OfficialHighresLoraSettings,
    OfficialLorasSettings,
    OfficialTurboLoraSettings,
    PromptRandomCollectSettings,
    QueueCancelRequest,
)
from .history import HistoryFlagsRequest, PublicSaveRequest
from .loras import LoraFavoriteRequest, LoraReviewRequest
from .reference import (
    I2IFromHistoryRequest,
    ImageToImageSettings,
    ReferenceAssistSettings,
    ReferenceModuleItemSettings,
    ReferenceModulesSettings,
)
from .settings import SettingsRequest

__all__ = [
    "DynamicPromptPreviewRequest",
    "DynamicPromptSettings",
    "FaceDetailerPostprocessRequest",
    "FaceDetailerRequestSettings",
    "FavoriteRequest",
    "GenerateRequest",
    "HandDetailerRequestSettings",
    "HandDetailerPostprocessRequest",
    "HistoryFlagsRequest",
    "I2IFromHistoryRequest",
    "ImageToImageSettings",
    "LoginRequest",
    "LoraFavoriteRequest",
    "LoraReviewRequest",
    "OriginalCharacterRequest",
    "OfficialHighresLoraSettings",
    "OfficialLorasSettings",
    "OfficialTurboLoraSettings",
    "PositivePromptFavoritePatch",
    "PositivePromptFavoriteRequest",
    "PromptConverterRequest",
    "PromptRandomCollectSettings",
    "PublicSaveRequest",
    "QueueCancelRequest",
    "ReferenceAssistSettings",
    "ReferenceModuleItemSettings",
    "ReferenceModulesSettings",
    "RecipeRequest",
    "SettingsRequest",
]
