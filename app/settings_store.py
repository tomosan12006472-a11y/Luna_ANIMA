from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any

from ._shared_utils import clamp_float, clamp_strength, normalize_lora_strengths
from .config import SETTINGS_PATH
from .face_detailer import DEFAULT_FACE_DETAILER_SETTINGS, DEFAULT_HAND_DETAILER_SETTINGS, sanitize_face_detailer_settings, sanitize_hand_detailer_settings
from .i2i_store import sanitize_image_to_image
from .official_lora_presets import infer_builtin_official_lora_preset_id, normalize_official_lora_preset_id, sanitize_official_loras
from .prompt_converter import DEFAULT_PROMPT_CONVERTER_SETTINGS, sanitize_prompt_converter_settings
from .public_save_finish import FINISH_PRESET_ID, sanitize_public_save_finish_settings
from .reference_modules import DEFAULT_REFERENCE_MODULES, sanitize_reference_modules
from .storage.json_store import JsonStore


_SETTINGS_LOCK = RLock()


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
        "mode": "text",
        "text": "@Luna_AIart_",
        "position": "bottom_right",
        "opacity": 0.72,
        "size": 36,
        "margin": 28,
        "signature_image_id": "",
        "signature_scale": 0.18,
    },
    "public_save": {
        "apply_watermark": True,
        "finish_enabled": False,
        "finish_preset": FINISH_PRESET_ID,
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
        "colorfix": {
            "enabled": False,
            "strength": 0.6,
        },
    },
    "official_lora_preset": "off",
    "turbo_restore_settings": {
        "steps": 32,
        "cfg": 4.5,
        "strength": 0.6,
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
    "hand_detailer": DEFAULT_HAND_DETAILER_SETTINGS,
    "prompt_converter": DEFAULT_PROMPT_CONVERTER_SETTINGS,
    "prompt_random_instruction_favorites": [],
    "ui": {
        "history_filter": "all",
    },
}

RATING_PROMPT_KEYS = {"safe", "sensitive", "nsfw", "explicit"}
QUALITY_PROMPT_KEYS = {"standard", "high", "character_check"}
PROMPT_RANDOM_FAVORITE_MODES = {"random", "positive_completion"}
PROMPT_RANDOM_FAVORITE_STRENGTHS = {"subtle", "standard", "reference_568", "legacy_568", "rich"}
PROMPT_RANDOM_FAVORITES_LIMIT = 80


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


def sanitize_prompt_random_instruction_favorites(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        instruction = str(raw.get("instruction") or "").strip()
        if not instruction:
            continue
        mode = str(raw.get("mode") or "random").strip().lower()
        if mode not in PROMPT_RANDOM_FAVORITE_MODES:
            mode = "random"
        strength = str(raw.get("strength") or "standard").strip().lower()
        if strength not in PROMPT_RANDOM_FAVORITE_STRENGTHS:
            strength = "standard"
        label = str(raw.get("label") or raw.get("title") or instruction[:32]).strip()[:80]
        if not label:
            label = instruction[:32]
        favorite_id = str(raw.get("id") or f"favorite_{len(result) + 1}").strip()[:80]
        include_characters = raw.get("include_characters") is not False
        result.append(
            {
                "id": favorite_id,
                "label": label,
                "instruction": instruction[:500],
                "mode": mode,
                "strength": strength,
                "include_characters": include_characters,
                "use_character_motifs": bool(include_characters and raw.get("use_character_motifs", True) is not False),
            }
        )
        if len(result) >= PROMPT_RANDOM_FAVORITES_LIMIT:
            break
    return result


def _safe_float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return number


def _safe_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def sanitize_watermark_settings(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    defaults = DEFAULT_APP_SETTINGS["watermark"]
    mode = str(raw.get("mode") or defaults["mode"]).strip().lower()
    if mode not in {"text", "signature_image"}:
        mode = "text"
    position = str(raw.get("position") or defaults["position"]).strip().lower()
    if position not in {"bottom_right", "bottom_left", "top_right", "top_left", "bottom_center"}:
        position = "bottom_right"
    return {
        "enabled": bool(raw.get("enabled", defaults["enabled"])),
        "mode": mode,
        "text": str(raw.get("text") or defaults["text"]).strip()[:120],
        "position": position,
        "opacity": clamp_float(_safe_float(raw.get("opacity"), defaults["opacity"]), defaults["opacity"], 0.0, 1.0),
        "size": int(clamp_float(_safe_int(raw.get("size"), defaults["size"]), defaults["size"], 10, 160)),
        "margin": int(clamp_float(_safe_int(raw.get("margin"), defaults["margin"]), defaults["margin"], 0, 256)),
        "signature_image_id": str(raw.get("signature_image_id") or "").strip()[:120],
        "signature_scale": clamp_float(_safe_float(raw.get("signature_scale"), defaults["signature_scale"]), defaults["signature_scale"], 0.02, 0.6),
    }


def sanitize_public_save_settings(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    finish = sanitize_public_save_finish_settings(
        {
            "finish_enabled": raw.get("finish_enabled", False),
            "finish_preset": raw.get("finish_preset", FINISH_PRESET_ID),
        }
    )
    return {
        "apply_watermark": bool(raw.get("apply_watermark", DEFAULT_APP_SETTINGS["public_save"]["apply_watermark"])),
        **finish,
    }


def sanitize_turbo_restore_settings(value: Any, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    base = fallback if isinstance(fallback, dict) else DEFAULT_APP_SETTINGS["turbo_restore_settings"]
    steps = int(clamp_float(_safe_float(raw.get("steps"), _safe_float(base.get("steps"), 32.0)), 32.0, 1.0, 100.0))
    cfg = clamp_float(_safe_float(raw.get("cfg"), _safe_float(base.get("cfg"), 4.5)), 4.5, 1.0, 20.0)
    strength = clamp_float(_safe_float(raw.get("strength"), _safe_float(base.get("strength"), 0.6)), 0.6, 0.0, 1.0)
    return {"steps": steps, "cfg": cfg, "strength": strength}


def sanitize_app_settings(settings: dict[str, Any]) -> dict[str, Any]:
    has_official_lora_preset = isinstance(settings, dict) and "official_lora_preset" in settings
    has_turbo_restore_settings = isinstance(settings, dict) and isinstance(settings.get("turbo_restore_settings"), dict)
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
    result["official_loras"] = sanitize_official_loras(result.get("official_loras"))
    result["watermark"] = sanitize_watermark_settings(result.get("watermark"))
    result["public_save"] = sanitize_public_save_settings(result.get("public_save"))
    result["official_lora_preset"] = (
        normalize_official_lora_preset_id(result.get("official_lora_preset"))
        if has_official_lora_preset
        else infer_builtin_official_lora_preset_id(result.get("official_loras"))
    )
    turbo = result["official_loras"].get("turbo", {})
    if has_turbo_restore_settings:
        restore_fallback = DEFAULT_APP_SETTINGS["turbo_restore_settings"]
        restore_source = settings.get("turbo_restore_settings")
    elif not turbo.get("enabled"):
        restore_fallback = {
            "steps": result.get("steps"),
            "cfg": result.get("cfg"),
            "strength": turbo.get("strength", 0.6),
        }
        restore_source = restore_fallback
    else:
        restore_fallback = DEFAULT_APP_SETTINGS["turbo_restore_settings"]
        restore_source = restore_fallback
    result["turbo_restore_settings"] = sanitize_turbo_restore_settings(restore_source, restore_fallback)
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
    result["hand_detailer"] = sanitize_hand_detailer_settings(result.get("hand_detailer"), mode="generation")
    result["prompt_converter"] = sanitize_prompt_converter_settings(result.get("prompt_converter"))
    result["prompt_random_instruction_favorites"] = sanitize_prompt_random_instruction_favorites(
        result.get("prompt_random_instruction_favorites")
    )
    return result


def load_app_settings() -> dict[str, Any]:
    with _SETTINGS_LOCK:
        return _load_app_settings_unlocked()


def _settings_default() -> dict[str, Any]:
    return deepcopy(DEFAULT_APP_SETTINGS)


def _validate_settings_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _settings_default()
    return sanitize_app_settings(data)


def _settings_store() -> JsonStore:
    return JsonStore(
        SETTINGS_PATH,
        default_factory=_settings_default,
        label="settings",
        lock=_SETTINGS_LOCK,
        validator=_validate_settings_payload,
    )


def _load_app_settings_unlocked() -> dict[str, Any]:
    return _settings_store().read(strict=True)


def save_app_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = sanitize_app_settings(settings)
    with _SETTINGS_LOCK:
        if SETTINGS_PATH.exists():
            _settings_store().read(strict=True)
        _settings_store().write(merged)
    return merged


def reset_app_settings() -> dict[str, Any]:
    settings = _settings_default()
    with _SETTINGS_LOCK:
        _settings_store().write(settings)
    return settings
