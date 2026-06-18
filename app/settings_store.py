from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import shutil
from threading import Lock
import time
from typing import Any

from ._shared_utils import clamp_float, clamp_strength, normalize_lora_strengths, write_json_atomic
from .config import SETTINGS_PATH
from .face_detailer import DEFAULT_FACE_DETAILER_SETTINGS, sanitize_face_detailer_settings
from .i2i_store import sanitize_image_to_image
from .prompt_converter import DEFAULT_PROMPT_CONVERTER_SETTINGS, sanitize_prompt_converter_settings
from .reference_modules import DEFAULT_REFERENCE_MODULES, sanitize_reference_modules


_SETTINGS_LOCK = Lock()


DEFAULT_APP_SETTINGS: dict[str, Any] = {
    "workflow_mode": "anima",
    "model": "Anima\\anima-preview3-base.safetensors",
    "text_encoder": "qwen_3_06b_base.safetensors",
    "vae": "qwen_image_vae.safetensors",
    "width": 1024,
    "height": 1536,
    "steps": 32,
    "cfg": 4.5,
    "shift": 4.0,
    "sampler": "er_sde",
    "scheduler": "simple",
    "seed_mode": "fixed",
    "seed": -1,
    "generation_count": 1,
    "default_common_prompt": "",
    "common_prompt_source": "default",
    "common_prompt_updated_at": None,
    "default_positive_prompt": "",
    "default_negative_prompt": "",
    "negative_prompt_mode": "append",
    "negative_prompt_source": "default",
    "negative_prompt_updated_at": None,
    "rating": "safe",
    "rating_prompt_overrides": {},
    "quality_preset": "standard",
    "quality_prompt_overrides": {},
    "negative_preset": "anima_recommended",
    "meta_prompt": "anime illustration",
    "year_prompt": "",
    "outfit_prompt": "",
    "expression_prompt": "",
    "pose_prompt": "",
    "background_prompt": "",
    "camera_prompt": "",
    "lighting_prompt": "",
    "natural_description": "",
    "loras": [],
    "lora_settings": {
        "slots": [
            {"slot": "character", "enabled": False, "lora_id": "none", "model_strength": 0.7, "clip_strength": 0.7},
            {"slot": "style", "enabled": False, "lora_id": "none", "model_strength": 0.25, "clip_strength": 0.25},
            {"slot": "official_hires", "enabled": False, "lora_id": "none", "model_strength": 0.6, "clip_strength": 0.6},
            {"slot": "turbo", "enabled": False, "lora_id": "none", "model_strength": 0.6, "clip_strength": 0.6},
        ],
    },
    "selected_character_mode": "single",
    "watermark": {
        "enabled": True,
        "text": "@Luna_AIart_",
        "position": "bottom_right",
        "opacity": 0.72,
        "size": 36,
        "margin": 28,
    },
    "public_save": {
        "apply_watermark": True,
    },
    "hires_fix": {
        "enabled": False,
        "mode": "latent",
        "latent_upscale_method": "nearest-exact",
        "upscale_method": "nearest-exact",
        "upscale_model": "4x-UltraSharp.pth",
        "upscale_factor": 1.5,
        "denoise": 0.4,
        "steps": 20,
        "target_width": 0,
        "target_height": 0,
    },
    "official_loras": {
        "highres": {
            "enabled": False,
            "strength": 0.6,
        },
        "turbo": {
            "enabled": False,
            "version": "auto",
            "strength": 0.6,
            "preset_applied": True,
        },
    },
    "reference_assist": {
        "enabled": False,
        "mode": "auto",
        "experimental": False,
        "image_id": "",
        "image_name": "",
        "controlnet_model": "",
        "strength": 0.25,
        "start_percent": 0.0,
        "end_percent": 0.65,
        "resize_mode": "fit",
        "union_type": "auto",
    },
    "reference_modules": DEFAULT_REFERENCE_MODULES,
    "image_to_image": {
        "enabled": False,
        "image_id": "",
        "source": "",
        "source_history_id": "",
        "denoise": 0.45,
        "resize_mode": "fit",
        "use_source_size": False,
        "allow_with_hires_fix": False,
        "allow_with_reference_assist": False,
    },
    "face_detailer": DEFAULT_FACE_DETAILER_SETTINGS,
    "prompt_converter": DEFAULT_PROMPT_CONVERTER_SETTINGS,
    "ui": {
        "history_filter": "all",
    },
}

RATING_PROMPT_KEYS = {"safe", "sensitive", "nsfw", "explicit"}
QUALITY_PROMPT_KEYS = {"standard", "high", "character_check"}


KNOWN_UPSCALE_MODELS = ["4x-AnimeSharp.pth", "4x-UltraSharp.pth", "4x_foolhardy_Remacri.pth"]
KNOWN_LATENT_METHODS = ["nearest-exact", "bilinear", "area", "bicubic", "bislerp", "lanczos"]


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def sanitize_lora_list(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        result.append(normalize_lora_strengths(dict(raw), 0.0))
    return result


def backup_broken_settings() -> None:
    if not SETTINGS_PATH.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = SETTINGS_PATH.with_name(f"settings.broken_{stamp}.json")
    shutil.move(str(SETTINGS_PATH), str(backup))


def sanitize_app_settings(settings: dict[str, Any]) -> dict[str, Any]:
    result = deep_merge(DEFAULT_APP_SETTINGS, settings)
    workflow_mode = str(result.get("workflow_mode") or "anima")
    if workflow_mode not in {"anima", "anima_mobile_extended", "anima_lora_sample"}:
        workflow_mode = "anima"
    result["workflow_mode"] = workflow_mode
    mode = str(result.get("negative_prompt_mode") or "append")
    if mode not in {"preset", "source", "custom", "append"}:
        mode = "append"
    result["negative_prompt_mode"] = "preset" if mode == "source" else mode
    raw_rating_overrides = result.get("rating_prompt_overrides")
    rating_overrides: dict[str, str] = {}
    if isinstance(raw_rating_overrides, dict):
        for key, value in raw_rating_overrides.items():
            clean_key = str(key or "").strip()
            if clean_key in RATING_PROMPT_KEYS:
                rating_overrides[clean_key] = str(value or "").strip()
    result["rating_prompt_overrides"] = rating_overrides
    raw_quality_overrides = result.get("quality_prompt_overrides")
    quality_overrides: dict[str, str] = {}
    if isinstance(raw_quality_overrides, dict):
        for key, value in raw_quality_overrides.items():
            clean_key = str(key or "").strip()
            if clean_key in QUALITY_PROMPT_KEYS:
                quality_overrides[clean_key] = str(value or "").strip()
    result["quality_prompt_overrides"] = quality_overrides
    result["shift"] = clamp_float(result.get("shift"), 4.0, 0.0, 100.0)
    hires = result.setdefault("hires_fix", {})
    mode = str(hires.get("mode") or "latent")
    legacy_method = str(hires.get("upscale_method") or "").strip()
    latent_method = str(hires.get("latent_upscale_method") or legacy_method or "nearest-exact").strip()
    if latent_method.startswith("Latent (") and latent_method.endswith(")"):
        latent_method = latent_method.removeprefix("Latent (").removesuffix(")")
    if latent_method not in KNOWN_LATENT_METHODS:
        latent_method = "nearest-exact"
    hires["latent_upscale_method"] = latent_method
    hires["upscale_method"] = latent_method

    upscale_model = str(hires.get("upscale_model") or "").strip()
    if not upscale_model or upscale_model.startswith("Latent"):
        upscale_model = "4x-UltraSharp.pth"
    hires["upscale_model"] = upscale_model
    hires["mode"] = "model" if mode == "model" else "latent"
    official = result.setdefault("official_loras", {})
    highres = official.setdefault("highres", {})
    turbo = official.setdefault("turbo", {})
    highres["enabled"] = bool(highres.get("enabled"))
    highres["strength"] = float(highres.get("strength") or 1.0)
    turbo["enabled"] = bool(turbo.get("enabled"))
    turbo["version"] = str(turbo.get("version") or "auto")
    turbo["strength"] = clamp_strength(turbo.get("strength"), 0.6)
    turbo["preset_applied"] = bool(turbo.get("preset_applied", True))
    highres["strength"] = clamp_strength(highres.get("strength"), 0.6)
    result["loras"] = sanitize_lora_list(result.get("loras"))
    lora_settings = result.setdefault("lora_settings", {})
    lora_settings["slots"] = sanitize_lora_list(lora_settings.get("slots"))
    reference = result.setdefault("reference_assist", {})
    reference["enabled"] = bool(reference.get("enabled"))
    reference["mode"] = str(reference.get("mode") or "auto")
    if reference["mode"] not in {"auto", "controlnet", "img2img_reference"}:
        reference["mode"] = "auto"
    reference["experimental"] = bool(reference.get("experimental"))
    reference["image_id"] = str(reference.get("image_id") or "")
    reference["image_name"] = str(reference.get("image_name") or "")
    reference["controlnet_model"] = str(reference.get("controlnet_model") or "")
    reference["strength"] = clamp_strength(reference.get("strength"), 0.25)
    reference["start_percent"] = clamp_strength(reference.get("start_percent"), 0.0)
    reference["end_percent"] = clamp_strength(reference.get("end_percent"), 0.65)
    reference["resize_mode"] = str(reference.get("resize_mode") or "fit")
    reference["union_type"] = str(reference.get("union_type") or "auto")
    result["reference_modules"] = sanitize_reference_modules(result.get("reference_modules"), app_scope="anima")
    result["image_to_image"] = sanitize_image_to_image(result.get("image_to_image"), app_scope="anima")
    result["face_detailer"] = sanitize_face_detailer_settings(result.get("face_detailer"), mode="generation")
    result["prompt_converter"] = sanitize_prompt_converter_settings(result.get("prompt_converter"))
    return result


def load_app_settings() -> dict[str, Any]:
    with _SETTINGS_LOCK:
        return _load_app_settings_unlocked()


def _load_app_settings_unlocked() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return deepcopy(DEFAULT_APP_SETTINGS)
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        time.sleep(0.05)
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            backup_broken_settings()
            return deepcopy(DEFAULT_APP_SETTINGS)
    if not isinstance(raw, dict):
        backup_broken_settings()
        return deepcopy(DEFAULT_APP_SETTINGS)
    return sanitize_app_settings(raw)


def save_app_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = sanitize_app_settings(settings)
    with _SETTINGS_LOCK:
        write_json_atomic(SETTINGS_PATH, merged)
    return merged


def reset_app_settings() -> dict[str, Any]:
    settings = deepcopy(DEFAULT_APP_SETTINGS)
    with _SETTINGS_LOCK:
        write_json_atomic(SETTINGS_PATH, settings)
    return settings
