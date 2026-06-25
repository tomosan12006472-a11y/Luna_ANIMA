from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from . import comfy_client
from .anima_adapter import load_settings
from .api import auth as auth_api
from .api import diagnostics as diagnostics_api
from .api import generation as generation_api
from .api import history as history_api
from .api import i2i as i2i_api
from .api import loras as loras_api
from .api import reference as reference_api
from .api import settings as settings_api
from .api import system as system_api
from .auth import SESSIONS, require_auth
from .config import ROOT_DIR, validate_startup_security
from .generation_helpers import reset_comfy_cache_for_character_prompt
from .generation_prepare import history_page_with_flags, refresh_pending_history_items
from .history_store import history_collection_revision, lite_history_item
from .responses import CachedStaticFiles, cached_file_response, resolve_public_save_watermark
from .schemas import (
    DynamicPromptPreviewRequest,
    FaceDetailerPostprocessRequest,
    FavoriteRequest,
    GenerateRequest,
    HandDetailerPostprocessRequest,
    HistoryFlagsRequest,
    I2IFromHistoryRequest,
    LoginRequest,
    LoraFavoriteRequest,
    LoraReviewRequest,
    OriginalCharacterRequest,
    PositivePromptFavoritePatch,
    PositivePromptFavoriteRequest,
    PromptConverterRequest,
    PublicSaveRequest,
    QueueCancelRequest,
    RecipeRequest,
    SettingsRequest,
)


def include_routers(app: FastAPI) -> None:
    for router in (
        auth_api.router,
        settings_api.router,
        generation_api.router,
        history_api.router,
        reference_api.router,
        i2i_api.router,
        loras_api.router,
        diagnostics_api.router,
        system_api.router,
    ):
        app.include_router(router)


def create_app() -> FastAPI:
    app = FastAPI(title="Luna ANIMA")
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.mount("/static", CachedStaticFiles(directory=ROOT_DIR / "app" / "static"), name="static")
    if hasattr(app, "add_event_handler"):
        app.add_event_handler("startup", validate_startup_security)
    else:
        app.on_event("startup")(validate_startup_security)
    include_routers(app)
    return app


app = create_app()

# Compatibility aliases for tests and scripts that imported endpoint helpers from app.main
# before the router split. New router code imports the concrete modules directly.
diagnostics = diagnostics_api.diagnostics
diagnostics_full = diagnostics_api.diagnostics_full


def history(*args: Any, **kwargs: Any) -> dict[str, Any]:
    history_api.load_settings = load_settings
    history_api.refresh_pending_history_items = refresh_pending_history_items
    history_api.history_page_with_flags = history_page_with_flags
    history_api.history_collection_revision = history_collection_revision
    history_api.lite_history_item = lite_history_item
    return history_api.history(*args, **kwargs)


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
    "SESSIONS",
    "SettingsRequest",
    "app",
    "cached_file_response",
    "create_app",
    "diagnostics",
    "diagnostics_full",
    "history",
    "include_routers",
    "require_auth",
    "reset_comfy_cache_for_character_prompt",
    "resolve_public_save_watermark",
]
