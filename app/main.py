from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import secrets
import time
import traceback
import uuid
from typing import Any

from fastapi import BackgroundTasks, Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import comfy_client
from . import i2i_store
from . import lora_catalog
from . import original_characters
from . import reference_store
from .config import ANIMA_HIGHRES_LORA_NAME, ANIMA_MAPPING_PATH, ANIMA_TURBO_LORA_V01_NAME, ANIMA_TURBO_LORA_V02_NAME, ANIMA_WORKFLOW_PATH, APP_PIN, CHARACTER_CATALOG_ROOT, COMFYUI_ADDR_DEFAULT, COMFYUI_ANIMA_TEMPLATE_PATH, COMFYUI_LORA_DIRS, MOBILE_PAYLOAD_DIR, ROOT_DIR
from .dynamic_prompt import expand_dynamic_prompt, list_wildcards
from .face_detailer import face_detailer_capabilities, sanitize_face_detailer_settings
from .generation_prepare import (
    face_detailer_capability_payload,
    generation_request_dict,
    history_page_with_flags,
    i2i_capability_payload,
    prepare_i2i_request,
    prepare_reference_modules_request,
    prepare_reference_request,
    refresh_pending_history_items,
    reference_capability_payload,
    reference_modules_availability_payload,
    reference_modules_model_status_payload,
    request_for_queue_item,
    save_completed_generation_history,
    save_mobile_payload_data,
)
from .favorites_store import add_favorite, load_favorites, localized_favorites, mark_favorite_used, remove_favorite
from .history_flags_store import (
    attach_flags_to_item,
    update_history_flags,
)
from .history_store import (
    copy_public_image,
    create_history_item,
    create_pending_history_item,
    enrich_history_item_from_payload,
    ensure_small_thumbnail,
    history_collection_revision,
    list_all_history_with_warnings,
    list_history,
    load_history_item,
    lite_history_item,
    update_pending_history_status,
)
from .model_info_cache import _object_choice, cached_object_info, model_cache_status as _model_cache_status
from .multipart_uploads import parse_multipart_file_upload
from .payload_builder import NEGATIVE_PRESETS, build_face_detailer_postprocess_payload, build_prompt_payload, build_prompts, compute_hires_size, find_lora_file, model_sampling_shift_metadata, official_lora_summary
from .positive_prompt_favorites_store import (
    add_positive_prompt_favorite,
    delete_positive_prompt_favorite,
    list_positive_prompt_favorites,
    mark_positive_prompt_favorite_used,
    update_positive_prompt_favorite,
)
from .positive_prompt_templates_store import list_positive_prompt_templates
from .prompt_converter import convert_prompt_text, prompt_converter_status
from .prompt_dictionary_store import prompt_dictionary_status, search_prompt_dictionary
from .prompt_random_collect import (
    attach_prompt_random_collect_items,
    collect_prompt_random_tags,
    prompt_random_collect_enabled,
    prompt_random_collect_status,
    sanitize_prompt_random_collect_request,
)
from .recipes_store import add_recipe, delete_recipe, list_recipes, mark_recipe_used
from .anima_adapter import catalog, load_settings
from .settings_store import load_app_settings, reset_app_settings, save_app_settings
from .validators import (
    error_response,
    validate_hires_fix,
    validate_image_to_image,
    validate_official_loras,
    validate_queue_count,
    validate_reference_modules,
)

class CachedStaticFiles(StaticFiles):
    def file_response(self, full_path: Any, stat_result: Any, scope: Any, status_code: int = 200) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app = FastAPI(title="Luna ANIMA")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/static", CachedStaticFiles(directory=ROOT_DIR / "app" / "static"), name="static")

SESSIONS: set[str] = set()

def cached_file_response(path: Path, media_type: str | None = None) -> FileResponse:
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=604800, immutable"},
    )

class LoginRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=32)


class GenerateRequest(BaseModel):
    workflow_mode: str = "anima"
    character1: str = "Random"
    character2: str = "None"
    character3: str = "None"
    character1_role: str = "main"
    character2_role: str = "left"
    character3_role: str = "right"
    original_character: str = "None"
    character1_weight: float = 1.0
    character2_weight: float = 1.0
    character3_weight: float = 1.0
    original_weight: float = 1.0
    rating: str = "safe"
    rating_prompt_overrides: dict[str, str] = Field(default_factory=dict)
    quality_preset: str = "standard"
    quality_prompt_overrides: dict[str, str] = Field(default_factory=dict)
    negative_preset: str = "anima_recommended"
    meta_prompt: str = "anime illustration"
    year_prompt: str = ""
    outfit_prompt: str = ""
    expression_prompt: str = ""
    pose_prompt: str = ""
    background_prompt: str = ""
    camera_prompt: str = ""
    lighting_prompt: str = ""
    natural_description: str = ""
    common_prompt: str = ""
    positive_prompt: str = ""
    negative_prompt: str = ""
    negative_prompt_raw: str = ""
    negative_prompt_mode: str = "append"
    prompt_ban: str = ""
    view_prompt: str = ""
    model: str = "Anima\\anima-preview3-base.safetensors"
    text_encoder: str = "qwen_3_06b_base.safetensors"
    vae: str = "qwen_image_vae.safetensors"
    width: int = 1024
    height: int = 1536
    steps: int = 32
    cfg: float = 4.5
    shift: float | None = None
    sampler: str = "er_sde"
    scheduler: str = "simple"
    seed_mode: str = "fixed"
    seed: int = -1
    loras: list[dict[str, Any]] = Field(default_factory=list)
    hires_fix: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    official_loras: dict[str, Any] = Field(default_factory=dict)
    reference_assist: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    reference_modules: dict[str, Any] = Field(default_factory=lambda: {"enabled": True})
    image_to_image: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    dynamic_prompt: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    prompt_random_collect: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    face_detailer: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    reset_comfy_cache: bool = False
    wait: bool = False
    count: int = 1


class FaceDetailerPostprocessRequest(BaseModel):
    history_id: str
    settings: dict[str, Any] = Field(default_factory=dict)


class DynamicPromptPreviewRequest(BaseModel):
    positive_prompt: str = ""
    negative_prompt: str = ""
    seed: int = 0
    enabled: bool = True


class PromptConverterRequest(BaseModel):
    source_text: str = Field("", max_length=4000)
    mode: str = "tags"
    existing_positive: str = Field("", max_length=8000)


class SettingsRequest(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)
    mode: str = "current"
    reason: str = "unspecified"


class PublicSaveRequest(BaseModel):
    apply_watermark: bool = False
    watermark: dict[str, Any] = Field(default_factory=dict)
    watermark_client: str = ""


def resolve_public_save_watermark(data: PublicSaveRequest, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if data.watermark_client == "current":
        watermark = dict(data.watermark) if data.apply_watermark else {"enabled": False}
        watermark["enabled"] = data.apply_watermark
        return watermark
    if data.apply_watermark:
        watermark = dict(data.watermark)
        watermark["enabled"] = True
        return watermark
    app_settings = settings if settings is not None else load_app_settings()
    configured = dict(app_settings.get("watermark") or {})
    public_save_settings = app_settings.get("public_save") if isinstance(app_settings.get("public_save"), dict) else {}
    configured["enabled"] = bool(public_save_settings.get("apply_watermark", configured.get("enabled", False)))
    return configured


class HistoryFlagsRequest(BaseModel):
    favorite: bool | None = None
    post_candidate: bool | None = None
    hidden: bool | None = None
    tags: list[str] | None = None
    patch: dict[str, Any] = Field(default_factory=dict)


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


class QueueCancelRequest(BaseModel):
    prompt_id: str = ""


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


class OriginalCharacterRequest(BaseModel):
    id: str = ""
    display_name: str = ""
    trigger_words: list[str] = Field(default_factory=list)
    positive_tags: list[str] = Field(default_factory=list)
    identity_prompt: str = ""
    negative_guard: str = ""
    default_lora: str | None = None
    favorite: bool = False


def _has_fixed_character_selection(data: Any) -> bool:
    def selected(value: Any) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized not in {"", "none", "random"}

    return any(
        selected(getattr(data, field, ""))
        for field in ("character1", "character2", "character3", "original_character")
    )


def reset_comfy_cache_for_character_prompt(addr: str, data: GenerateRequest) -> JSONResponse | None:
    if not data.reset_comfy_cache:
        return None
    if not _has_fixed_character_selection(data):
        return None
    try:
        queue = comfy_client.queue_info(addr)
    except Exception as exc:
        return error_response(
            status_code=502,
            message="Failed to inspect ComfyUI queue before cache reset.",
            stage="comfy_cache_reset_queue_check",
            data=data,
            comfy_response_text=str(exc),
            retryable=True,
        )
    if queue.get("queue_running") or queue.get("queue_pending"):
        return error_response(
            status_code=409,
            message="ComfyUI cache reset was skipped because the queue is not empty.",
            stage="comfy_cache_reset_queue_check",
            data=data,
            retryable=True,
        )
    result = comfy_client.reset_execution_cache(addr)
    if result.get("ok"):
        return None
    return error_response(
        status_code=502,
        message="Failed to reset ComfyUI execution cache before character generation.",
        stage="comfy_cache_reset",
        data=data,
        comfy_status=result.get("status"),
        comfy_response_text=str(result.get("text") or ""),
        retryable=True,
    )


def require_auth(session: str | None) -> None:
    if session not in SESSIONS:
        raise HTTPException(status_code=401, detail="login required")


def _pending_history_by_prompt_id() -> dict[str, dict[str, Any]]:
    items, _warnings = list_all_history_with_warnings()
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        status = str(item.get("status") or "")
        prompt_id = str(item.get("prompt_id") or "")
        if status in {"queued", "running"} and prompt_id:
            result[prompt_id] = item
    return result


def _looks_like_prompt_id(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) < 8:
        return False
    return "-" in text or all(char in "0123456789abcdefABCDEF" for char in text)


def _queue_entry_prompt_id(entry: Any) -> str:
    if isinstance(entry, dict):
        for key in ("prompt_id", "id"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                return value
    if isinstance(entry, (list, tuple)):
        for index in (1, 0):
            if index < len(entry) and isinstance(entry[index], str) and _looks_like_prompt_id(entry[index]):
                return entry[index]
        for value in entry:
            prompt_id = _queue_entry_prompt_id(value)
            if prompt_id:
                return prompt_id
    return ""


def _queue_rows(entries: Any, history_by_prompt_id: dict[str, dict[str, Any]], *, include_position: bool) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        prompt_id = _queue_entry_prompt_id(entry)
        history_item = history_by_prompt_id.get(prompt_id)
        row: dict[str, Any] = {
            "prompt_id": prompt_id,
            "ours": bool(history_item),
        }
        if include_position:
            row["position"] = index + 1
        if history_item:
            row["history_id"] = history_item.get("id") or history_item.get("history_id")
        rows.append(row)
    return rows


def _float_input_spec(info: dict[str, Any] | None, class_name: str, input_name: str) -> dict[str, Any]:
    if not info:
        return {}
    node_info = info.get(class_name) if isinstance(info.get(class_name), dict) else {}
    input_info = node_info.get("input") if isinstance(node_info.get("input"), dict) else {}
    for group in ("required", "optional"):
        values = input_info.get(group) if isinstance(input_info.get(group), dict) else {}
        value = values.get(input_name)
        if isinstance(value, list) and len(value) > 1 and isinstance(value[1], dict):
            return value[1]
    return {}


def anima_shift_capability(addr: str | None = None, info: dict[str, Any] | None = None) -> dict[str, Any]:
    local = model_sampling_shift_metadata({})
    class_name = str(local.get("node_class") or "ModelSamplingAuraFlow")
    input_name = str(local.get("input_name") or "shift")
    object_info_error = ""
    cache: dict[str, Any] = {}
    if info is None and addr:
        try:
            info, cache = cached_object_info(addr)
        except Exception as exc:
            object_info_error = str(exc)
            info = None
    spec = _float_input_spec(info, class_name, input_name)
    object_has_node = bool(info and class_name in info)
    object_has_input = bool(spec)
    warnings = list(local.get("warnings") or [])
    if info is not None and not object_has_node:
        warnings.append(f"{class_name} is not available in ComfyUI object_info.")
    if info is not None and object_has_node and not object_has_input:
        warnings.append(f"{class_name}.{input_name} is not available in ComfyUI object_info.")
    if object_info_error:
        warnings.append(f"object_info unavailable: {object_info_error}")
    supported = bool(local.get("supported") and (info is None or object_has_input))
    return {
        **local,
        "supported": supported,
        "min": spec.get("min"),
        "max": spec.get("max"),
        "step": spec.get("step"),
        "object_info_default": spec.get("default"),
        "object_info_node_found": object_has_node,
        "object_info_input_found": object_has_input,
        "cache": cache,
        "warnings": warnings,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(
        ROOT_DIR / "app" / "static" / "index.html",
        headers={"Cache-Control": "no-cache, max-age=0, must-revalidate"},
    )


@app.post("/api/login")
def login(data: LoginRequest, response: Response) -> dict[str, Any]:
    if data.pin != APP_PIN:
        raise HTTPException(status_code=403, detail="PINが違います")
    token = secrets.token_urlsafe(24)
    SESSIONS.add(token)
    response.set_cookie("anima_claude_session", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return {"ok": True}


@app.get("/api/bootstrap")
def bootstrap(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    app_settings = load_app_settings()
    return {
        "ok": True,
        "character_catalog_root": str(CHARACTER_CATALOG_ROOT),
        "character_select_settings": settings,
        "anima_workflow": str(ANIMA_WORKFLOW_PATH),
        "anima_mapping": str(ANIMA_MAPPING_PATH),
        "catalog_count": len(catalog.wai),
        "custom_count": len(catalog.custom),
        "original_count": len(catalog.original),
        "settings": app_settings,
        "anima_shift": anima_shift_capability(),
        "negative_presets": NEGATIVE_PRESETS,
        "defaults": {
            "api_addr": settings.get("api_addr") or COMFYUI_ADDR_DEFAULT,
            "workflow_mode": app_settings.get("workflow_mode", "anima"),
            "common_prompt": app_settings.get("default_common_prompt", ""),
            "positive_prompt": app_settings.get("default_positive_prompt", ""),
            "negative_prompt": app_settings.get("default_negative_prompt", ""),
            "negative_prompt_mode": app_settings.get("negative_prompt_mode", "append"),
            "width": app_settings.get("width", settings.get("width", 1024)),
            "height": app_settings.get("height", 1536),
            "steps": app_settings.get("steps", 32),
            "cfg": app_settings.get("cfg", 4.5),
            "shift": app_settings.get("shift", anima_shift_capability().get("default", 4.0)),
            "sampler": app_settings.get("sampler", "er_sde"),
            "scheduler": app_settings.get("scheduler", "simple"),
            "seed": app_settings.get("seed", settings.get("random_seed", -1)),
            "model": app_settings.get("model", "Anima\\anima-preview3-base.safetensors"),
            "text_encoder": app_settings.get("text_encoder", "qwen_3_06b_base.safetensors"),
            "vae": app_settings.get("vae", "qwen_image_vae.safetensors"),
        },
    }


@app.get("/api/settings")
def get_settings(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "settings": load_app_settings()}


@app.post("/api/settings")
def post_settings(data: SettingsRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "mode": data.mode, "reason": data.reason, "settings": save_app_settings(data.settings)}


@app.post("/api/settings/reset")
def post_settings_reset(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "settings": reset_app_settings()}


@app.get("/api/catalog")
def search_catalog(
    q: str = "",
    kind: str = "all",
    limit: int = 80,
    offset: int = 0,
    anima_claude_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    require_auth(anima_claude_session)
    page = catalog.search_page(q, kind, max(1, min(limit, 300)), max(0, offset))
    return {"ok": True, **page}


def original_character_lora_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    terms = {str(item.get("id") or "").lower(), str(item.get("display_name") or "").lower()}
    terms.update(str(term).lower() for term in item.get("trigger_words") or [])
    terms = {term for term in terms if term}
    candidates: list[dict[str, Any]] = []
    catalog_data = lora_catalog.catalog_with_favorites(lora_catalog.load_catalog())
    for lora in lora_catalog.selectable_loras(catalog_data):
        blob = " ".join(
            str(value or "")
            for value in [
                lora.get("lora_id"),
                lora.get("display_name"),
                lora.get("file_name"),
                lora.get("relative_path"),
                lora.get("notes"),
                " ".join(lora.get("trained_words") or []),
                " ".join(lora.get("tags") or []),
            ]
        ).lower()
        if any(term in blob for term in terms):
            candidates.append(lora)
    return candidates[:12]


@app.get("/api/original-characters")
def get_original_characters(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    payload = original_characters.original_characters_payload()
    for item in payload["items"]:
        item["lora_candidates"] = original_character_lora_candidates(item)
    return payload


@app.post("/api/original-characters")
def post_original_character(data: OriginalCharacterRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = original_characters.upsert_original_character(data.model_dump())
    catalog.reload()
    return {"ok": True, "item": item, **original_characters.original_characters_payload()}


@app.put("/api/original-characters/{character_id}")
def put_original_character(character_id: str, data: OriginalCharacterRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    raw = data.model_dump()
    raw["id"] = character_id
    item = original_characters.upsert_original_character(raw)
    catalog.reload()
    return {"ok": True, "item": item, **original_characters.original_characters_payload()}


@app.get("/api/favorites")
def favorites(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    data = localized_favorites(load_favorites())
    return {"ok": True, **data}


def localized_favorite_item(favorite: dict[str, Any] | None) -> dict[str, Any] | None:
    if not favorite:
        return None
    key = "original_characters" if favorite.get("source") == "original_character" else "characters"
    payload = localized_favorites(
        {
            "characters": [favorite] if key == "characters" else [],
            "original_characters": [favorite] if key == "original_characters" else [],
        }
    )
    return payload[key][0] if payload[key] else None


@app.post("/api/favorites")
def post_favorite(data: FavoriteRequest, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        action, favorite, favorites_data = add_favorite(data.model_dump())
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "status": 400, "stage": "validate_favorite", "message": str(exc), "source": data.source},
        )
    return JSONResponse(status_code=200, content={"ok": True, "status": "ok", "action": action, "favorite": localized_favorite_item(favorite), **localized_favorites(favorites_data)})


@app.delete("/api/favorites/{source}/{favorite_id}")
def delete_favorite(source: str, favorite_id: str, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        removed, favorites_data = remove_favorite(source, favorite_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "status": 400, "stage": "validate_favorite", "message": str(exc), "source": source},
        )
    return JSONResponse(status_code=200, content={"ok": True, "status": "ok", "removed": removed, **localized_favorites(favorites_data)})


@app.post("/api/favorites/{source}/{favorite_id}/use")
def use_favorite(source: str, favorite_id: str, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    favorite = mark_favorite_used(source, favorite_id)
    return JSONResponse(status_code=200, content={"ok": True, "favorite": localized_favorite_item(favorite), **localized_favorites(load_favorites())})


@app.get("/api/prompts/positive-favorites")
def positive_prompt_favorites(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    data = list_positive_prompt_favorites()
    return {"ok": True, "count": len(data["items"]), **data}


@app.post("/api/prompts/positive-favorites")
def post_positive_prompt_favorite(data: PositivePromptFavoriteRequest, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        item = add_positive_prompt_favorite(data.model_dump())
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "status": 400, "stage": "positive_prompt_favorite_add", "message": str(exc)})
    payload = list_positive_prompt_favorites()
    return JSONResponse(status_code=201, content={"ok": True, "item": item, "count": len(payload["items"]), **payload})


@app.patch("/api/prompts/positive-favorites/{favorite_id}")
def patch_positive_prompt_favorite(favorite_id: str, data: PositivePromptFavoritePatch, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        item = update_positive_prompt_favorite(favorite_id, data.model_dump(exclude_unset=True))
    except KeyError:
        return JSONResponse(status_code=404, content={"ok": False, "status": 404, "stage": "positive_prompt_favorite_update", "message": "Favorite not found"})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "status": 400, "stage": "positive_prompt_favorite_update", "message": str(exc)})
    payload = list_positive_prompt_favorites()
    return JSONResponse(status_code=200, content={"ok": True, "item": item, "count": len(payload["items"]), **payload})


@app.delete("/api/prompts/positive-favorites/{favorite_id}")
def delete_positive_prompt_favorite_route(favorite_id: str, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    removed = delete_positive_prompt_favorite(favorite_id)
    payload = list_positive_prompt_favorites()
    return JSONResponse(status_code=200, content={"ok": True, "removed": removed, "count": len(payload["items"]), **payload})


@app.post("/api/prompts/positive-favorites/{favorite_id}/used")
def use_positive_prompt_favorite(favorite_id: str, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        item = mark_positive_prompt_favorite_used(favorite_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"ok": False, "status": 404, "stage": "positive_prompt_favorite_used", "message": "Favorite not found"})
    payload = list_positive_prompt_favorites()
    return JSONResponse(status_code=200, content={"ok": True, "item": item, "count": len(payload["items"]), **payload})


@app.get("/api/recipes")
def recipes(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    payload = list_recipes()
    return {"ok": True, "count": len(payload["items"]), **payload}


@app.post("/api/recipes")
def post_recipe(data: RecipeRequest, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        item = add_recipe(data.name, data.summary, data.request)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "status": 400, "stage": "recipe_add", "message": str(exc)})
    payload = list_recipes()
    return JSONResponse(status_code=201, content={"ok": True, "item": item, "count": len(payload["items"]), **payload})


@app.delete("/api/recipes/{recipe_id}")
def delete_recipe_route(recipe_id: str, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "removed": delete_recipe(recipe_id)}


@app.post("/api/recipes/{recipe_id}/used")
def use_recipe(recipe_id: str, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        item = mark_recipe_used(recipe_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"ok": False, "status": 404, "stage": "recipe_used", "message": "Recipe not found"})
    return JSONResponse(status_code=200, content={"ok": True, "item": item})


@app.get("/api/prompts/positive-templates")
def positive_prompt_templates(
    query: str = Query("", max_length=160),
    category: str = Query("", max_length=80),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    anima_claude_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return list_positive_prompt_templates(query=query, category=category, limit=limit, offset=offset)


@app.get("/api/prompt-dictionary/status")
def prompt_dictionary_status_route(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return prompt_dictionary_status()


@app.get("/api/prompt-dictionary/search")
def prompt_dictionary_search_route(
    q: str = Query("", max_length=160),
    limit: int = Query(50, ge=1, le=50),
    anima_claude_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return search_prompt_dictionary(q, limit=limit)


@app.get("/api/prompt-converter/status")
def prompt_converter_status_route(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, **prompt_converter_status(load_app_settings().get("prompt_converter"))}


@app.post("/api/prompt-converter/convert")
def prompt_converter_convert_route(data: PromptConverterRequest, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    result = convert_prompt_text(
        load_app_settings().get("prompt_converter"),
        source_text=data.source_text,
        mode=data.mode,
        existing_positive=data.existing_positive,
        app_scope="anima",
        catalog_entries=[*catalog.wai, *catalog.original],
    )
    if not result.get("ok"):
        return JSONResponse(status_code=int(result.get("status") or 502), content=result)
    return JSONResponse(status_code=200, content=result)


@app.get("/api/prompt-random-collect/status")
def prompt_random_collect_status_route(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, **prompt_random_collect_status(load_app_settings())}


@app.get("/api/dynamic-prompts/wildcards")
def dynamic_prompt_wildcards(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {
        "ok": True,
        **list_wildcards(
            config_dir=ROOT_DIR / "config" / "dynamic_prompt_wildcards",
            user_dir=ROOT_DIR / "user_data" / "dynamic_prompt_wildcards",
        ),
    }


@app.post("/api/dynamic-prompts/preview")
def dynamic_prompt_preview(data: DynamicPromptPreviewRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {
        "ok": True,
        **expand_dynamic_prompt(
            positive_prompt=data.positive_prompt,
            negative_prompt=data.negative_prompt,
            seed=data.seed,
            enabled=data.enabled,
            config_dir=ROOT_DIR / "config" / "dynamic_prompt_wildcards",
            user_dir=ROOT_DIR / "user_data" / "dynamic_prompt_wildcards",
        ),
    }


@app.get("/api/models")
def models(addr: str = COMFYUI_ADDR_DEFAULT, refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    try:
        info, cache = cached_object_info(addr, refresh=refresh)
    except Exception as exc:
        return {"ok": False, "message": str(exc), "models": [], "samplers": [], "schedulers": [], "loras": [], "upscale_models": [], "upscale_methods": [], "cache": _model_cache_status(addr)}
    unets = _object_choice(info, "DiffusionModelLoaderKJ", "model_name")
    if not unets:
        unets = _object_choice(info, "UNETLoader", "unet_name")
    clips = _object_choice(info, "CLIPLoader", "clip_name")
    vaes = _object_choice(info, "VAELoader", "vae_name")
    ckpt = _object_choice(info, "CheckpointLoaderSimple", "ckpt_name")
    ksampler = info.get("KSampler", {}).get("input", {}).get("required", {})
    samplers = ksampler.get("sampler_name", [[]])[0]
    schedulers = ksampler.get("scheduler", [[]])[0]
    loras = _object_choice(info, "LoraLoader", "lora_name")
    upscale_models = _object_choice(info, "UpscaleModelLoader", "model_name")
    upscale_methods = _object_choice(info, "LatentUpscaleBy", "upscale_method")
    controlnet_models = _object_choice(info, "ControlNetLoader", "control_net_name")
    if not upscale_methods:
        upscale_methods = ["nearest-exact", "bilinear", "bicubic", "lanczos", "area"]
    return {
        "ok": True,
        "models": unets or ckpt,
        "checkpoints": ckpt,
        "text_encoders": clips,
        "vaes": vaes,
        "samplers": samplers,
        "schedulers": schedulers,
        "loras": loras,
        "upscale_models": upscale_models,
        "upscale_methods": upscale_methods,
        "controlnet_models": controlnet_models,
        "cache": cache,
    }


@app.get("/api/reference/capabilities")
def reference_capabilities(refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    payload = reference_capability_payload(addr, refresh=refresh)
    payload.setdefault("reference_assist", {})["anima_payload_guard"] = "experimental_required"
    return payload


@app.get("/api/reference-modules/availability")
def reference_modules_availability(refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    return reference_modules_availability_payload(addr, refresh=refresh)


@app.get("/api/reference-modules/model-status")
def reference_modules_model_status(refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    return reference_modules_model_status_payload(addr, refresh=refresh)


@app.get("/api/face-detailer/capabilities")
def face_detailer_capability_endpoint(refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    return face_detailer_capability_payload(addr, refresh=refresh)


@app.get("/api/reference/images")
def reference_images(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "items": reference_store.list_reference_images()}


@app.get("/api/reference-modules/images")
def reference_module_images(module: str = "outfit", anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "items": reference_store.list_reference_images(module=module)}


@app.post("/api/reference/upload")
async def reference_upload(request: Request, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    try:
        filename, raw = parse_multipart_file_upload(request.headers.get("content-type", ""), await request.body())
        item = reference_store.save_reference_upload(filename or "reference.png", raw, app_scope="anima")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    upload_result = comfy_client.upload_image(addr, filename=item["filename"], data=Path(item["path"]).read_bytes())
    if upload_result.get("ok"):
        item = reference_store.update_comfy_upload(item["image_id"], upload_result) or item
    return {
        "ok": True,
        "item": item,
        "comfyui_upload": {
            "ok": bool(upload_result.get("ok")),
            "status": upload_result.get("status"),
            "message": str(upload_result.get("text") or "")[:500],
        },
    }


@app.post("/api/reference-modules/upload")
async def reference_module_upload(request: Request, module: str = "outfit", anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    if module not in {"outfit", "pose"}:
        raise HTTPException(status_code=400, detail="Only outfit and pose reference module uploads are implemented.")
    try:
        filename, raw = parse_multipart_file_upload(request.headers.get("content-type", ""), await request.body())
        default_name = "pose_reference.png" if module == "pose" else "outfit_reference.png"
        item = reference_store.save_reference_upload(filename or default_name, raw, app_scope="anima", module=module)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    upload_result = comfy_client.upload_image(addr, filename=item["filename"], data=Path(item["path"]).read_bytes())
    if upload_result.get("ok"):
        item = reference_store.update_comfy_upload(item["image_id"], upload_result) or item
    return {
        "ok": True,
        "item": item,
        "items": reference_store.list_reference_images(module=module),
        "comfyui_upload": {
            "ok": bool(upload_result.get("ok")),
            "status": upload_result.get("status"),
            "message": str(upload_result.get("text") or "")[:500],
        },
    }


@app.post("/api/reference-modules/clear")
def reference_module_clear(module: str = "outfit", anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    if module not in {"outfit", "pose"}:
        raise HTTPException(status_code=400, detail="Only outfit and pose reference modules are implemented.")
    return {"ok": True, "module": module, "items": reference_store.list_reference_images(module=module)}


@app.get("/api/reference/images/{image_id}/image")
def reference_image(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = reference_store.get_reference_image(image_id)
    if not item:
        raise HTTPException(status_code=404, detail="reference image not found")
    path = Path(str(item.get("path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="reference image file not found")
    return FileResponse(path)


@app.get("/api/reference/images/{image_id}/thumbnail")
def reference_thumbnail(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = reference_store.get_reference_image(image_id)
    if not item:
        raise HTTPException(status_code=404, detail="reference image not found")
    path = Path(str(item.get("thumbnail_path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="reference thumbnail not found")
    return FileResponse(path)


@app.delete("/api/reference/images/{image_id}")
def reference_delete(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "deleted": reference_store.delete_reference_image(image_id)}


@app.get("/api/i2i/capabilities")
def i2i_capabilities_endpoint(refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    return i2i_capability_payload(addr, refresh=refresh)


@app.get("/api/i2i/images")
def i2i_images(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "items": i2i_store.list_i2i_images(limit=limit, offset=offset)}


@app.post("/api/i2i/upload")
async def i2i_upload(request: Request, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    try:
        filename, raw = parse_multipart_file_upload(request.headers.get("content-type", ""), await request.body())
        item = i2i_store.save_i2i_upload(filename or "i2i.png", raw, app_scope="anima")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "item": item}


class I2IFromHistoryRequest(BaseModel):
    history_id: str


@app.post("/api/i2i/from-history")
def i2i_from_history(data: I2IFromHistoryRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = load_history_item(data.history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    path = Path(str(item.get("image_path") or ""))
    try:
        i2i_item = i2i_store.save_i2i_from_path(path, app_scope="anima", source_history_id=str(item.get("id") or data.history_id))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "item": i2i_item}


@app.get("/api/i2i/images/{image_id}/image")
def i2i_image(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = i2i_store.get_i2i_image(image_id)
    if not item:
        raise HTTPException(status_code=404, detail="i2i image not found")
    path = Path(str(item.get("path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="i2i image file not found")
    return FileResponse(path)


@app.get("/api/i2i/images/{image_id}/thumbnail")
def i2i_thumbnail(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = i2i_store.get_i2i_image(image_id)
    if not item:
        raise HTTPException(status_code=404, detail="i2i image not found")
    path = Path(str(item.get("thumbnail_path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="i2i thumbnail not found")
    return FileResponse(path)


@app.delete("/api/i2i/images/{image_id}")
def i2i_delete(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "deleted": i2i_store.delete_i2i_image(image_id)}


def comfy_visible_loras(addr: str | None = None, refresh: bool = False) -> list[str]:
    try:
        info, _cache = cached_object_info(addr or COMFYUI_ADDR_DEFAULT, refresh=refresh)
    except Exception:
        return []
    loras = _object_choice(info, "LoraLoaderModelOnly", "lora_name")
    if not loras:
        loras = _object_choice(info, "LoraLoader", "lora_name")
    return loras


@app.get("/api/loras/catalog")
def get_lora_catalog(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    catalog_data = lora_catalog.catalog_with_favorites(lora_catalog.load_catalog())
    return {"ok": True, **catalog_data, "selectable": lora_catalog.selectable_loras(catalog_data), "slot_defaults": lora_catalog.SLOT_DEFAULTS}


@app.post("/api/loras/catalog/refresh")
def refresh_lora_catalog(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    catalog_data = lora_catalog.catalog_with_favorites(lora_catalog.refresh_catalog())
    return {"ok": True, **catalog_data, "selectable": lora_catalog.selectable_loras(catalog_data), "slot_defaults": lora_catalog.SLOT_DEFAULTS}


@app.get("/api/loras/favorites")
def get_lora_favorites(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return lora_catalog.list_lora_favorites()


@app.post("/api/loras/favorites/toggle")
def toggle_lora_favorite(data: LoraFavoriteRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    result = lora_catalog.set_lora_favorite(data.model_dump(), data.favorite)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "LoRA favorite update failed")
    return result


@app.post("/api/loras/favorites/add")
def add_lora_favorite(data: LoraFavoriteRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    result = lora_catalog.set_lora_favorite(data.model_dump(), True)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "LoRA favorite add failed")
    return result


@app.post("/api/loras/favorites/remove")
def remove_lora_favorite(data: LoraFavoriteRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return lora_catalog.set_lora_favorite(data.model_dump(), False)


@app.get("/api/loras/diagnostics")
def lora_diagnostics(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    return {"ok": True, **lora_catalog.diagnostics(comfy_visible_loras(settings.get("api_addr") or COMFYUI_ADDR_DEFAULT))}


@app.get("/api/loras/discovery/fate/characters")
def lora_discovery_fate_characters(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return lora_catalog.read_discovery_file("fate_characters.json")


@app.get("/api/loras/discovery/fate/candidates")
def lora_discovery_fate_candidates(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return lora_catalog.read_discovery_file("fate_candidates_normalized.json")


@app.post("/api/loras/discovery/fate/review")
def lora_discovery_review(data: LoraReviewRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return lora_catalog.review_candidate(data.candidate_id, data.review_status, data.app_scope, data.note)


@app.post("/api/loras/discovery/fate/download-approved")
def lora_download_approved(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {
        "ok": False,
        "status": "review_required",
        "message": "Approved-only LoRA download is intentionally disabled in this MVP endpoint. Use tools/download_approved_loras.py after reviewing candidates.",
    }


def prompt_random_collect_error_response(result: dict[str, Any]) -> JSONResponse:
    status_code = int(result.get("status") or 502)
    return JSONResponse(status_code=status_code, content=result)


def apply_prompt_random_collect_or_error(request_data_items: list[dict[str, Any]]) -> JSONResponse | None:
    if not request_data_items:
        return None
    feature = request_data_items[0].get("prompt_random_collect")
    feature_config = sanitize_prompt_random_collect_request(feature)
    if not prompt_random_collect_enabled(feature_config):
        return None
    include_characters = bool(feature_config.get("include_characters", True))
    contexts: list[dict[str, Any]] = []
    for position, request_data in enumerate(request_data_items):
        prompts = build_prompts(request_data)
        contexts.append(
            {
                "index": int(request_data.get("queue_index") or position),
                "seed": prompts.get("seed", request_data.get("seed")),
                "characters": prompts.get("characters", []) if include_characters else [],
                "existing_positive": prompts.get("positive", ""),
            }
        )
    result = collect_prompt_random_tags(load_app_settings(), feature=feature_config, contexts=contexts, app_scope="anima")
    if not result.get("ok"):
        return prompt_random_collect_error_response(result)
    attach_prompt_random_collect_items(request_data_items, result)
    return None


@app.post("/api/payload/preview")
def payload_preview(data: GenerateRequest, anima_claude_session: str | None = Cookie(default=None)) -> Any:
    require_auth(anima_claude_session)
    invalid_count = validate_queue_count(data)
    if invalid_count:
        return invalid_count
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    invalid = validate_hires_fix(data, addr)
    if invalid:
        return invalid
    invalid_loras = validate_official_loras(data, addr)
    if invalid_loras:
        return invalid_loras
    invalid_i2i = validate_image_to_image(data)
    if invalid_i2i:
        return invalid_i2i
    invalid_ref_modules = validate_reference_modules(data, addr)
    if invalid_ref_modules:
        return invalid_ref_modules
    client_id = f"anima-claude-preview-{uuid.uuid4()}"
    request_data = generation_request_dict(data)
    request_data["queue_index"] = 0
    random_error = apply_prompt_random_collect_or_error([request_data])
    if random_error:
        return random_error
    request_data = prepare_reference_request(request_data, addr, upload=False)
    request_data = prepare_reference_modules_request(request_data, addr, upload=False)
    request_data = prepare_i2i_request(request_data, addr, upload=True)
    payload = build_prompt_payload(request_data, client_id)
    prompts = build_prompts(request_data)
    size = compute_hires_size(request_data)
    shift_info = anima_shift_capability(addr)
    request_shift_info = request_data.get("model_sampling", {}) if isinstance(request_data.get("model_sampling"), dict) else {}
    shift_info = {
        **shift_info,
        "shift": request_shift_info.get("shift", shift_info.get("shift")),
        "shift_source": request_shift_info.get("shift_source", shift_info.get("shift_source")),
        "request_supported": request_shift_info.get("supported"),
        "request_warnings": request_shift_info.get("warnings", []),
    }
    return {
        "ok": True,
        "payload": payload,
        "prompts": prompts,
        "size": size,
        "official_loras": official_lora_summary(request_data),
        "loras": request_data.get("loras", []),
        "reference_assist": request_data.get("reference_assist", {"enabled": False}),
        "reference_modules": request_data.get("reference_modules", {}),
        "image_to_image": request_data.get("image_to_image", {"enabled": False}),
        "face_detailer": request_data.get("face_detailer", {"enabled": False}),
        "prompt_random_collect": request_data.get("prompt_random_collect", {"enabled": False}),
        "anima_shift": shift_info,
        "shift": shift_info.get("shift"),
        "shift_supported": bool(shift_info.get("supported")),
    }


@app.post("/api/generate")
def generate(
    data: GenerateRequest,
    background_tasks: BackgroundTasks,
    anima_claude_session: str | None = Cookie(default=None),
) -> JSONResponse:
    require_auth(anima_claude_session)
    invalid_count = validate_queue_count(data)
    if invalid_count:
        return invalid_count
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    invalid = validate_hires_fix(data, addr)
    if invalid:
        return invalid
    invalid_loras = validate_official_loras(data, addr)
    if invalid_loras:
        return invalid_loras
    invalid_i2i = validate_image_to_image(data)
    if invalid_i2i:
        return invalid_i2i
    invalid_ref_modules = validate_reference_modules(data, addr)
    if invalid_ref_modules:
        return invalid_ref_modules
    cache_reset_error = reset_comfy_cache_for_character_prompt(addr, data)
    if cache_reset_error:
        return cache_reset_error
    if not data.wait:
        items: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        item_requests = []
        request_data_items: list[dict[str, Any]] = []
        for index in range(data.count):
            item_request = request_for_queue_item(data, index, wait=False)
            request_data = generation_request_dict(item_request)
            request_data["queue_index"] = index
            item_requests.append(item_request)
            request_data_items.append(request_data)
        random_error = apply_prompt_random_collect_or_error(request_data_items)
        if random_error:
            return random_error
        for index, (item_request, request_data) in enumerate(zip(item_requests, request_data_items)):
            request_data = prepare_reference_request(request_data, addr, upload=True)
            request_data = prepare_reference_modules_request(request_data, addr, upload=True)
            request_data = prepare_i2i_request(request_data, addr, upload=True)
            client_id = f"anima-claude-{uuid.uuid4()}"
            try:
                payload = build_prompt_payload(request_data, client_id)
                dump_path = save_mobile_payload_data(payload, request_data, item_request.workflow_mode)
                prompts = build_prompts(request_data)
            except Exception as exc:
                errors.append(
                    {
                        "index": index,
                        "stage": "build_payload",
                        "message": str(exc),
                        "traceback_short": "".join(traceback.format_exception_only(type(exc), exc)).strip(),
                    }
                )
                break
            result = comfy_client.run_generation(addr, payload, wait=False)
            if result.ok:
                pending_item = None
                if result.prompt_id:
                    pending_item = create_pending_history_item(
                        request_data=request_data,
                        prompts=prompts,
                        prompt_id=result.prompt_id,
                        payload_path=dump_path,
                        workflow_mode=item_request.workflow_mode,
                        index=index,
                    )
                    background_tasks.add_task(
                        save_completed_generation_history,
                        addr=addr,
                        request_data=request_data,
                        prompts=prompts,
                        prompt_id=result.prompt_id,
                        payload_path=str(dump_path),
                        workflow_mode=item_request.workflow_mode,
                        history_id=pending_item["id"],
                    )
                items.append(
                    {
                        "index": index,
                        "prompt_id": result.prompt_id,
                        "seed": prompts.get("seed"),
                        "status": "queued",
                        "history_id": pending_item["id"] if pending_item else None,
                        "payload_dump": str(dump_path),
                        "prompt_random_collect": request_data.get("prompt_random_collect", {"enabled": False}),
                    }
                )
            else:
                errors.append(
                    {
                        "index": index,
                        "stage": result.stage or "submit_prompt",
                        "message": result.error or "generation failed",
                        "comfy_status": result.status,
                        "comfy_response_text": result.response_text or "",
                        "comfy_node_errors": result.node_errors,
                    }
                )
        response_status = "queued" if len(items) == data.count and not errors else "partial" if items else "failed"
        return JSONResponse(
            status_code=200 if items else 502,
            content={
                "ok": bool(items),
                "status": response_status,
                "count": data.count,
                "queued_count": len(items),
                "items": items,
                "errors": errors,
                "size": compute_hires_size(generation_request_dict(data)),
                "official_loras": official_lora_summary(generation_request_dict(data)),
                "prompt_random_collect": request_data_items[0].get("prompt_random_collect", {"enabled": False}) if request_data_items else {"enabled": False},
                "reference_assist": generation_request_dict(data).get("reference_assist", {"enabled": False}),
                "reference_modules": generation_request_dict(data).get("reference_modules", {}),
                "image_to_image": generation_request_dict(data).get("image_to_image", {"enabled": False}),
                "anima_shift": generation_request_dict(data).get("model_sampling", {}),
                "shift": generation_request_dict(data).get("shift"),
            },
        )
    client_id = f"anima-claude-{uuid.uuid4()}"
    request_data = generation_request_dict(data)
    request_data["queue_index"] = 0
    random_error = apply_prompt_random_collect_or_error([request_data])
    if random_error:
        return random_error
    request_data = prepare_reference_request(request_data, addr, upload=True)
    request_data = prepare_reference_modules_request(request_data, addr, upload=True)
    request_data = prepare_i2i_request(request_data, addr, upload=True)
    try:
        payload = build_prompt_payload(request_data, client_id)
        dump_path = save_mobile_payload_data(payload, request_data, data.workflow_mode)
        prompts = build_prompts(request_data)
    except Exception as exc:
        traceback.print_exc()
        return error_response(
            status_code=400,
            message=str(exc),
            stage="build_payload",
            data=data,
            traceback_short="".join(traceback.format_exception_only(type(exc), exc)).strip(),
            retryable=False,
        )
    result = comfy_client.run_generation(addr, payload, wait=data.wait)
    history_item = None
    if result.ok and data.wait:
        try:
            history_item = create_history_item(
                request_data=request_data,
                prompts=prompts,
                result=result,
                payload_path=dump_path,
                workflow_mode=data.workflow_mode,
            )
        except Exception as exc:
            traceback.print_exc()
            return error_response(
                status_code=502,
                message=str(exc),
                stage="history_save",
                data=data,
                traceback_short="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                retryable=False,
            )
    if not result.ok:
        return error_response(
            status_code=502,
            message=result.error or "generation failed",
            stage=result.stage or "comfy_response",
            data=data,
            comfy_status=result.status,
            comfy_response_text=result.response_text or "",
            comfy_node_errors=result.node_errors,
            traceback_short=result.traceback_short,
            retryable=True,
        )
    status = 200 if result.ok else 502
    return JSONResponse(
        status_code=status,
        content={
            "ok": result.ok,
            "prompt_id": result.prompt_id,
            "image_url": result.image_url,
            "image_data_url": result.image_data_url,
            "error": result.error,
            "response_text": result.response_text,
            "payload_dump": str(dump_path),
            "history_item": history_item,
            "size": compute_hires_size(request_data),
            "official_loras": official_lora_summary(request_data),
            "reference_assist": request_data.get("reference_assist", {"enabled": False}),
            "image_to_image": request_data.get("image_to_image", {"enabled": False}),
            "prompt_random_collect": request_data.get("prompt_random_collect", {"enabled": False}),
            "anima_shift": request_data.get("model_sampling", {}),
            "shift": request_data.get("shift"),
        },
    )


@app.get("/api/queue")
def queue_status(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    try:
        queue = comfy_client.queue_info(addr)
    except Exception as exc:
        return {"ok": False, "message": str(exc), "running": [], "pending": []}
    history_by_prompt_id = _pending_history_by_prompt_id()
    running = _queue_rows(queue.get("queue_running"), history_by_prompt_id, include_position=False)
    pending = _queue_rows(queue.get("queue_pending"), history_by_prompt_id, include_position=True)
    return {"ok": True, "running": running, "pending": pending}


@app.post("/api/queue/cancel")
def queue_cancel(data: QueueCancelRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    prompt_id = str(data.prompt_id or "").strip()
    if not prompt_id:
        return {"ok": False, "message": "prompt_id is required"}
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    result = comfy_client.queue_delete(addr, [prompt_id])
    if not result.get("ok"):
        return {"ok": False, "message": result.get("text") or "ComfyUI queue delete failed", "result": result}
    history_item = _pending_history_by_prompt_id().get(prompt_id)
    updated = None
    if history_item and history_item.get("id"):
        updated = update_pending_history_status(str(history_item["id"]), "failed", "Cancelled by user")
    return {
        "ok": True,
        "result": result,
        "history_id": history_item.get("id") if history_item else None,
        "history_updated": bool(updated),
    }


@app.post("/api/queue/interrupt")
def queue_interrupt(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    result = comfy_client.interrupt(addr)
    if not result.get("ok"):
        return {"ok": False, "message": result.get("text") or "ComfyUI interrupt failed", "result": result}
    return {"ok": True, "result": result}


@app.get("/api/history")
def history(
    response: Response,
    limit: int = 100,
    offset: int = 0,
    view: str = "",
    filter_name: str = Query("all", alias="filter"),
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    model: str = "",
    lora: str = "",
    seed: str = "",
    hires_mode: str = "",
    reference: str = "",
    sampler: str = "",
    scheduler: str = "",
    rating: str = "",
    character: str = "",
    known_revision: str = "",
    anima_claude_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    search_filters = {
        "q": q,
        "date_from": date_from,
        "date_to": date_to,
        "model": model,
        "lora": lora,
        "seed": seed,
        "hires_mode": hires_mode,
        "reference": reference,
        "sampler": sampler,
        "scheduler": scheduler,
        "rating": rating,
        "character": character,
    }
    search_filters = {key: value for key, value in search_filters.items() if str(value or "").strip()}
    items, warnings, summary, total = history_page_with_flags(limit, offset, filter_name, search_filters)
    if refresh_pending_history_items(addr, items):
        items, warnings, summary, total = history_page_with_flags(limit, offset, filter_name, search_filters)
    normalized_offset = max(0, int(offset or 0))
    response_items = [lite_history_item(item) for item in items] if str(view or "").lower() == "list" else items
    latest = response_items[0] if response_items else {}
    latest_id = str(latest.get("id") or "")
    latest_created_at = str(latest.get("created_at") or "")
    response_limit = max(1, min(int(limit or 100), 100))
    revision = ":".join(
        [
            history_collection_revision(),
            str(view or ""),
            str(filter_name or "all"),
            str(response_limit),
            str(normalized_offset),
            json.dumps(search_filters, ensure_ascii=False, sort_keys=True),
        ]
    )
    response.headers["Cache-Control"] = "no-store, max-age=0"
    if str(known_revision or "").strip() == revision:
        return {"ok": True, "unchanged": True, "revision": revision}
    return {
        "ok": True,
        "unchanged": False,
        "items": response_items,
        "warnings": warnings,
        "summary": summary,
        "total": total,
        "filtered_total": total,
        "query": {"filter": filter_name or "all", **search_filters, **({"view": "list"} if str(view or "").lower() == "list" else {})},
        "limit": response_limit,
        "offset": normalized_offset,
        "has_more": normalized_offset + len(items) < total,
        "latest_id": latest_id,
        "latest_created_at": latest_created_at,
        "revision": revision,
    }


@app.get("/api/history/{history_id}")
def history_detail(history_id: str, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    enrich_history_item_from_payload(item)
    attach_flags_to_item(item)
    return {"ok": True, "item": item}


def face_detailer_history_prompts(item: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    dynamic_prompt = item.get("dynamic_prompt") if isinstance(item.get("dynamic_prompt"), dict) else {}
    positive = str(dynamic_prompt.get("expanded_positive_prompt") or item.get("positive") or "")
    negative = str(dynamic_prompt.get("expanded_negative_prompt") or item.get("negative") or "")
    return positive, negative, dynamic_prompt or None


def build_face_detailer_postprocess_request(item: dict[str, Any], settings: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []
    positive, negative, dynamic_prompt = face_detailer_history_prompts(item)
    app_settings = load_app_settings()
    text_encoder = str(item.get("text_encoder") or app_settings.get("text_encoder") or "qwen_3_06b_base.safetensors")
    vae = str(item.get("vae") or app_settings.get("vae") or "qwen_image_vae.safetensors")
    if not item.get("text_encoder"):
        warnings.append("History text encoder is missing; using current saved text encoder.")
    if not item.get("vae"):
        warnings.append("History VAE is missing; using current saved VAE.")
    if not positive:
        warnings.append("History positive prompt is missing.")
    face_settings = sanitize_face_detailer_settings(settings, mode="postprocess")
    face_settings["enabled"] = True
    face_settings["mode"] = "postprocess"
    request_data = {
        "operation": "face_detailer_postprocess",
        "parent_history_id": item.get("id"),
        "source_image": {
            "history_id": item.get("id"),
            "filename": item.get("filename"),
            "type": "output",
        },
        "workflow_mode": "face_detailer_postprocess",
        "model": item.get("model") or app_settings.get("model") or "Anima\\anima-preview3-base.safetensors",
        "text_encoder": text_encoder,
        "vae": vae,
        "width": item.get("output_width") or item.get("width") or 1024,
        "height": item.get("output_height") or item.get("height") or 1536,
        "steps": item.get("steps") or 32,
        "cfg": item.get("cfg") or 4.5,
        "shift": item.get("shift") if item.get("shift") is not None else app_settings.get("shift", 4.0),
        "model_sampling": item.get("model_sampling") or {},
        "sampler": item.get("sampler") or "er_sde",
        "scheduler": item.get("scheduler") or "simple",
        "seed": item.get("seed", -1),
        "positive_prompt": positive,
        "negative_prompt": negative,
        "negative_prompt_raw": negative,
        "negative_prompt_mode": "custom",
        "common_prompt": item.get("common") or "",
        "rating": item.get("rating") or "safe",
        "natural_description": item.get("natural_description") or "",
        "loras": item.get("loras") or [],
        "official_loras": item.get("official_loras") or {"highres": {"enabled": False}, "turbo": {"enabled": False}},
        "hires_fix": {"enabled": False},
        "reference_assist": {"enabled": False},
        "dynamic_prompt": dynamic_prompt if dynamic_prompt else {"enabled": False},
        "face_detailer": face_settings,
    }
    request_data["model_sampling"] = model_sampling_shift_metadata(request_data)
    request_data["shift"] = request_data["model_sampling"].get("shift")
    prompts = {"seed": request_data["seed"], "positive": positive, "negative": negative, "rating": request_data["rating"], "natural_description": request_data["natural_description"]}
    if dynamic_prompt:
        prompts["dynamic_prompt"] = dynamic_prompt
    return request_data, prompts, warnings


@app.post("/api/face-detailer/postprocess")
def face_detailer_postprocess(
    data: FaceDetailerPostprocessRequest,
    background_tasks: BackgroundTasks,
    anima_claude_session: str | None = Cookie(default=None),
) -> JSONResponse:
    require_auth(anima_claude_session)
    item = load_history_item(data.history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    image_path = Path(str(item.get("image_path") or ""))
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="source image not found")
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    caps = face_detailer_capability_payload(addr).get("face_detailer", {})
    if not caps.get("supported"):
        return JSONResponse(status_code=400, content={"ok": False, "message": "FaceDetailer is not available.", "face_detailer": caps})
    request_data, prompts, warnings = build_face_detailer_postprocess_request(item, data.settings)
    digest = hashlib.sha256(f"{item.get('id')}:{time.time()}".encode("utf-8")).hexdigest()[:10]
    upload_name = f"anima_face_detailer_{item.get('id')}_{digest}{image_path.suffix or '.png'}"
    upload_result = comfy_client.upload_image(addr, filename=upload_name, data=image_path.read_bytes(), overwrite=True)
    if not upload_result.get("ok"):
        return JSONResponse(status_code=502, content={"ok": False, "message": "Failed to upload source image to ComfyUI.", "upload": upload_result})
    uploaded = upload_result.get("json") if isinstance(upload_result.get("json"), dict) else {}
    image_name = str(uploaded.get("name") or upload_name)
    client_id = f"anima-face-detailer-{uuid.uuid4()}"
    try:
        payload = build_face_detailer_postprocess_payload(request_data, client_id, image_name)
        dump_path = save_mobile_payload_data(payload, request_data, "face_detailer_postprocess")
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(status_code=400, content={"ok": False, "message": str(exc), "stage": "build_face_detailer_payload"})
    result = comfy_client.run_generation(addr, payload, wait=False)
    if not result.ok:
        return JSONResponse(status_code=502, content={"ok": False, "message": result.error or "FaceDetailer queue failed", "stage": result.stage, "comfy_node_errors": result.node_errors})
    pending_item = None
    if result.prompt_id:
        pending_item = create_pending_history_item(
            request_data=request_data,
            prompts=prompts,
            prompt_id=result.prompt_id,
            payload_path=dump_path,
            workflow_mode="face_detailer_postprocess",
            index=0,
        )
        background_tasks.add_task(
            save_completed_generation_history,
            addr=addr,
            request_data=request_data,
            prompts=prompts,
            prompt_id=result.prompt_id,
            payload_path=str(dump_path),
            workflow_mode="face_detailer_postprocess",
            history_id=pending_item["id"],
        )
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "queued": True,
            "prompt_id": result.prompt_id,
            "pending_history_id": pending_item["id"] if pending_item else None,
            "parent_history_id": item.get("id"),
            "warnings": warnings,
            "face_detailer": request_data.get("face_detailer", {}),
        },
    )


@app.post("/api/history/{history_id}/flags")
def history_flags(history_id: str, data: HistoryFlagsRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    patch = dict(data.patch or {})
    for key in ("favorite", "post_candidate", "hidden", "tags"):
        value = getattr(data, key)
        if value is not None:
            patch[key] = value
    item["flags"] = update_history_flags(history_id, patch)
    return {"ok": True, "item": item, "flags": item["flags"]}


@app.get("/api/history/{history_id}/image")
def history_image(history_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    path = Path(item["image_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="image not found")
    return cached_file_response(path)


@app.get("/api/history/{history_id}/thumbnail")
def history_thumbnail(history_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    path = Path(item["thumbnail_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="thumbnail not found")
    return cached_file_response(path, media_type="image/jpeg")


@app.get("/api/history/{history_id}/thumbnail-small")
def history_thumbnail_small(history_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    path = ensure_small_thumbnail(item)
    if not path or not path.exists():
        fallback = Path(str(item.get("thumbnail_path") or ""))
        if not fallback.exists():
            raise HTTPException(status_code=404, detail="thumbnail not found")
        return cached_file_response(fallback, media_type="image/jpeg")
    return cached_file_response(path, media_type="image/jpeg")


@app.get("/api/history/{history_id}/public-image")
def history_public_image(history_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    public_path = item.get("public_save", {}).get("path")
    if not public_path:
        raise HTTPException(status_code=404, detail="public image not found")
    path = Path(public_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="public image not found")
    return cached_file_response(path)


@app.post("/api/history/{history_id}/public-save")
def public_save(history_id: str, data: PublicSaveRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    watermark = resolve_public_save_watermark(data)
    public_info = copy_public_image(item, watermark)
    updated = load_history_item(history_id) or item
    public_image_url = updated.get("public_image_url") or public_info.get("url")
    return {
        "ok": True,
        "public_save": public_info,
        "public_image_url": public_image_url,
        "filename": public_info.get("filename") or f"{history_id}_public.png",
        "item": updated,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "app": "Luna ANIMA",
        "character_catalog_root_exists": CHARACTER_CATALOG_ROOT.exists(),
        "catalog_count": len(catalog.wai),
        "custom_count": len(catalog.custom),
    }


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _workflow_source_diagnostics() -> dict[str, Any]:
    mapping = _load_json_file(ANIMA_MAPPING_PATH)
    source = mapping.get("workflow_source") if isinstance(mapping.get("workflow_source"), dict) else {}
    source_path = Path(str(source.get("source_path") or COMFYUI_ANIMA_TEMPLATE_PATH))
    warning = ""
    if "ComfyUI_MobilePanel" in str(source_path) or "ComfyUI_MobilePanel" in str(ANIMA_WORKFLOW_PATH):
        warning = "Current ANIMA workflow source appears to be ComfyUI_MobilePanel. Use ComfyUI-side ANIMAテンプレ instead."
    return {
        "current_workflow_path": str(ANIMA_WORKFLOW_PATH),
        "source_type": source.get("source_type") or "comfyui_template",
        "source_name": source.get("source_name") or "ANIMAテンプレ",
        "source_path": str(source_path),
        "source_exists": source_path.exists(),
        "source_sha256": source.get("source_sha256") or _file_sha256(source_path),
        "source_modified_time": datetime.fromtimestamp(source_path.stat().st_mtime).isoformat(timespec="seconds") if source_path.exists() else "",
        "copied_workflow_sha256": _file_sha256(ANIMA_WORKFLOW_PATH),
        "warning": warning,
    }


def _mapping_diagnostics() -> dict[str, Any]:
    mapping = _load_json_file(ANIMA_MAPPING_PATH)
    workflow = _load_json_file(ANIMA_WORKFLOW_PATH)
    required_keys = [
        "positive_prompt",
        "negative_prompt",
        "width",
        "height",
        "diffusion_model",
        "text_encoder",
        "vae",
        "model_sampling",
        "seed",
        "steps",
        "cfg",
        "sampler_name",
        "scheduler",
        "save_prefix",
    ]
    found: dict[str, bool] = {}
    missing: list[str] = []
    for key in required_keys:
        node_id = str((mapping.get(key) or {}).get("node_id") or "")
        ok = bool(node_id and node_id in workflow)
        found[key] = ok
        if not ok:
            missing.append(key)
    return {"path": str(ANIMA_MAPPING_PATH), "required_node_ids_found": found, "missing": missing}


def _official_lora_diagnostics(info: dict[str, Any] | None = None) -> dict[str, Any]:
    highres_path = find_lora_file(ANIMA_HIGHRES_LORA_NAME)
    turbo_v02_path = find_lora_file(ANIMA_TURBO_LORA_V02_NAME)
    turbo_v01_path = find_lora_file(ANIMA_TURBO_LORA_V01_NAME)
    turbo_file = ANIMA_TURBO_LORA_V02_NAME if turbo_v02_path else ANIMA_TURBO_LORA_V01_NAME
    lora_loader = ""
    visible: list[str] = []
    if info:
        if "LoraLoaderModelOnly" in info:
            lora_loader = "LoraLoaderModelOnly"
            visible = _object_choice(info, "LoraLoaderModelOnly", "lora_name")
        else:
            loaders = sorted([name for name in info if "lora" in name.lower()])
            lora_loader = loaders[0] if loaders else ""
    return {
        "highres_lora_found": bool(highres_path),
        "highres_lora_file": ANIMA_HIGHRES_LORA_NAME,
        "highres_lora_path": highres_path,
        "highres_visible_to_comfy": ANIMA_HIGHRES_LORA_NAME in visible if visible else False,
        "turbo_lora_found": bool(turbo_v02_path or turbo_v01_path),
        "turbo_lora_file": turbo_file,
        "turbo_lora_path": turbo_v02_path or turbo_v01_path,
        "turbo_lora_version": "v0.2" if turbo_v02_path else "v0.1" if turbo_v01_path else "",
        "turbo_visible_to_comfy": turbo_file in visible if visible else False,
        "lora_loader_node_type": lora_loader,
        "lora_dirs": [str(path) for path in COMFYUI_LORA_DIRS],
    }


@app.get("/api/diagnostics")
def diagnostics(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    return {
        "ok": True,
        "diagnostics_mode": "light",
        "character_catalog_root": str(CHARACTER_CATALOG_ROOT),
        "character_catalog_root_exists": CHARACTER_CATALOG_ROOT.exists(),
        "catalog_count": len(catalog.wai),
        "custom_count": len(catalog.custom),
        "original_count": len(catalog.original),
        "api_addr": addr,
        "mobile_payload_dir": str(MOBILE_PAYLOAD_DIR),
        "anima_workflow_found": ANIMA_WORKFLOW_PATH.exists(),
        "anima_mapping_found": ANIMA_MAPPING_PATH.exists(),
        "models_cache": _model_cache_status(addr),
        "anima_shift": anima_shift_capability(addr),
        "reference_assist": reference_capability_payload(addr).get("reference_assist", {}),
        "face_detailer": face_detailer_capability_payload(addr).get("face_detailer", {}),
        "history_count": len(list_history(500)),
        "settings_path": str(ROOT_DIR / "user_data" / "settings.json"),
    }


@app.get("/api/diagnostics/full")
def diagnostics_full(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    model_status: dict[str, Any] = {}
    info: dict[str, Any] | None = None
    try:
        info, _cache = cached_object_info(addr, refresh=True)
        model_status = {
            "anima_model_found": "Anima\\anima-preview3-base.safetensors" in _object_choice(info, "DiffusionModelLoaderKJ", "model_name"),
            "legacy_anima_model_found": "Anima\\anima-base-v1.0.safetensors" in _object_choice(info, "DiffusionModelLoaderKJ", "model_name"),
            "text_encoder_found": "qwen_3_06b_base.safetensors" in _object_choice(info, "CLIPLoader", "clip_name"),
            "vae_found": "qwen_image_vae.safetensors" in _object_choice(info, "VAELoader", "vae_name"),
        }
    except Exception as exc:
        model_status = {"error": str(exc)}
    official_loras = _official_lora_diagnostics(info)
    shift_info = anima_shift_capability(addr, info)
    return {
        "ok": True,
        "diagnostics_mode": "full",
        "character_catalog_root": str(CHARACTER_CATALOG_ROOT),
        "character_catalog_root_exists": CHARACTER_CATALOG_ROOT.exists(),
        "catalog_count": len(catalog.wai),
        "custom_count": len(catalog.custom),
        "original_count": len(catalog.original),
        "api_addr": addr,
        "mobile_payload_dir": str(MOBILE_PAYLOAD_DIR),
        "anima_workflow_found": ANIMA_WORKFLOW_PATH.exists(),
        "anima_mapping_found": ANIMA_MAPPING_PATH.exists(),
        "models_cache": _model_cache_status(addr),
        "workflow_source": _workflow_source_diagnostics(),
        "mapping": _mapping_diagnostics(),
        "models": model_status,
        "anima_shift": shift_info,
        "reference_assist": reference_store.reference_capabilities(info or {}).get("reference_assist", {}) if info else reference_capability_payload(addr).get("reference_assist", {}),
        "face_detailer": face_detailer_capabilities(info or {}) if info else face_detailer_capability_payload(addr).get("face_detailer", {}),
        "official_loras": official_loras,
        "highres_lora_found": official_loras["highres_lora_found"],
        "highres_lora_file": official_loras["highres_lora_file"],
        "turbo_lora_found": official_loras["turbo_lora_found"],
        "turbo_lora_file": official_loras["turbo_lora_file"],
        "turbo_lora_version": official_loras["turbo_lora_version"],
        "lora_loader_node_type": official_loras["lora_loader_node_type"],
        "workflow_mode": "ANIMA txt2img queue-only workflow",
        "luna_features": "not used",
        "history_count": len(list_history(500)),
        "settings_path": str(ROOT_DIR / "user_data" / "settings.json"),
        "loras": lora_catalog.diagnostics(comfy_visible_loras(addr)),
    }
