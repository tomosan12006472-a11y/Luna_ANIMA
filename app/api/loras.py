from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie, HTTPException

from .. import lora_catalog
from ..anima_adapter import load_settings
from ..auth import require_auth
from ..capabilities import comfy_visible_loras
from ..config import COMFYUI_ADDR_DEFAULT
from ..schemas.loras import LoraFavoriteRequest, LoraReviewRequest

router = APIRouter()

@router.get("/api/loras/catalog")
def get_lora_catalog(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    catalog_data = lora_catalog.catalog_with_favorites(lora_catalog.load_catalog())
    return {"ok": True, **catalog_data, "selectable": lora_catalog.selectable_loras(catalog_data), "slot_defaults": lora_catalog.SLOT_DEFAULTS}


@router.post("/api/loras/catalog/refresh")
def refresh_lora_catalog(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    catalog_data = lora_catalog.catalog_with_favorites(lora_catalog.refresh_catalog())
    return {"ok": True, **catalog_data, "selectable": lora_catalog.selectable_loras(catalog_data), "slot_defaults": lora_catalog.SLOT_DEFAULTS}


@router.get("/api/loras/favorites")
def get_lora_favorites(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return lora_catalog.list_lora_favorites()


@router.post("/api/loras/favorites/toggle")
def toggle_lora_favorite(data: LoraFavoriteRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    result = lora_catalog.set_lora_favorite(data.model_dump(), data.favorite)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "LoRA favorite update failed")
    return result


@router.post("/api/loras/favorites/add")
def add_lora_favorite(data: LoraFavoriteRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    result = lora_catalog.set_lora_favorite(data.model_dump(), True)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "LoRA favorite add failed")
    return result


@router.post("/api/loras/favorites/remove")
def remove_lora_favorite(data: LoraFavoriteRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return lora_catalog.set_lora_favorite(data.model_dump(), False)


@router.get("/api/loras/diagnostics")
def lora_diagnostics(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    return {"ok": True, **lora_catalog.diagnostics(comfy_visible_loras(settings.get("api_addr") or COMFYUI_ADDR_DEFAULT))}


@router.get("/api/loras/discovery/fate/characters")
def lora_discovery_fate_characters(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return lora_catalog.read_discovery_file("fate_characters.json")


@router.get("/api/loras/discovery/fate/candidates")
def lora_discovery_fate_candidates(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return lora_catalog.read_discovery_file("fate_candidates_normalized.json")


@router.post("/api/loras/discovery/fate/review")
def lora_discovery_review(data: LoraReviewRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return lora_catalog.review_candidate(data.candidate_id, data.review_status, data.app_scope, data.note)


@router.post("/api/loras/discovery/fate/download-approved")
def lora_download_approved(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {
        "ok": False,
        "status": "review_required",
        "message": "Approved-only LoRA download is intentionally disabled in this MVP endpoint. Use tools/download_approved_loras.py after reviewing candidates.",
    }
