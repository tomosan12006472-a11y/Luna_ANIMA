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

from fastapi import BackgroundTasks, Cookie, FastAPI, HTTPException, Query, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import comfy_client
from . import i2i_store
from . import lora_catalog
from . import original_characters
from . import reference_store
from .config import ANIMA_HIGHRES_LORA_NAME, ANIMA_MAPPING_PATH, ANIMA_TURBO_LORA_V01_NAME, ANIMA_TURBO_LORA_V02_NAME, ANIMA_WORKFLOW_PATH, APP_PIN, CHARACTER_CATALOG_ROOT, COMFYUI_ADDR_DEFAULT, COMFYUI_ANIMA_TEMPLATE_PATH, COMFYUI_LORA_DIRS, MOBILE_PAYLOAD_DIR, ROOT_DIR, validate_startup_security
from .dynamic_prompt import expand_dynamic_prompt, list_wildcards
from .face_detailer import face_detailer_capabilities, sanitize_face_detailer_settings, sanitize_hand_detailer_settings
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
from .payload_builder import NEGATIVE_PRESETS, build_face_detailer_postprocess_payload, build_hand_detailer_postprocess_payload, build_prompt_payload, build_prompts, compute_hires_size, find_lora_file, model_sampling_shift_metadata, official_lora_summary
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


@app.on_event("startup")
def validate_startup_security_event() -> None:
    validate_startup_security()

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
    hand_detailer: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    reset_comfy_cache: bool = False
    wait: bool = False
    count: int = 1


class FaceDetailerPostprocessRequest(BaseModel):
    history_id: str
    settings: dict[str, Any] = Field(default_factory=dict)


class HandDetailerPostprocessRequest(BaseModel):
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










































































class I2IFromHistoryRequest(BaseModel):
    history_id: str










def comfy_visible_loras(addr: str | None = None, refresh: bool = False) -> list[str]:
    try:
        info, _cache = cached_object_info(addr or COMFYUI_ADDR_DEFAULT, refresh=refresh)
    except Exception:
        return []
    loras = _object_choice(info, "LoraLoaderModelOnly", "lora_name")
    if not loras:
        loras = _object_choice(info, "LoraLoader", "lora_name")
    return loras
























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


def build_hand_detailer_postprocess_request(item: dict[str, Any], settings: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
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
    hand_settings = sanitize_hand_detailer_settings(settings, mode="postprocess")
    hand_settings["enabled"] = True
    hand_settings["mode"] = "postprocess"
    request_data = {
        "operation": "hand_detailer_postprocess",
        "parent_history_id": item.get("id"),
        "source_image": {
            "history_id": item.get("id"),
            "filename": item.get("filename"),
            "type": "output",
        },
        "workflow_mode": "hand_detailer_postprocess",
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
        "face_detailer": {"enabled": False},
        "hand_detailer": hand_settings,
    }
    request_data["model_sampling"] = model_sampling_shift_metadata(request_data)
    request_data["shift"] = request_data["model_sampling"].get("shift")
    prompts = {"seed": request_data["seed"], "positive": positive, "negative": negative, "rating": request_data["rating"], "natural_description": request_data["natural_description"]}
    if dynamic_prompt:
        prompts["dynamic_prompt"] = dynamic_prompt
    return request_data, prompts, warnings




















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

from .api import auth as auth_api
from .api import diagnostics as diagnostics_api
from .api import generation as generation_api
from .api import history as history_api
from .api import i2i as i2i_api
from .api import loras as loras_api
from .api import reference as reference_api
from .api import settings as settings_api

for router in (
    auth_api.router,
    settings_api.router,
    generation_api.router,
    history_api.router,
    reference_api.router,
    i2i_api.router,
    loras_api.router,
    diagnostics_api.router,
):
    app.include_router(router)

for _api_module in (auth_api, settings_api, generation_api, history_api, reference_api, i2i_api, loras_api, diagnostics_api):
    for _route in _api_module.router.routes:
        _endpoint = getattr(_route, "endpoint", None)
        _name = getattr(_endpoint, "__name__", "")
        if _name:
            globals().setdefault(_name, _endpoint)
