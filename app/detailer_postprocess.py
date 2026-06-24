from __future__ import annotations

from typing import Any

from .face_detailer import sanitize_face_detailer_settings, sanitize_hand_detailer_settings
from .payload_builder import model_sampling_shift_metadata
from .settings_store import load_app_settings


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
        "official_loras": item.get("official_loras")
        or {"highres": {"enabled": False}, "turbo": {"enabled": False}, "colorfix": {"enabled": False}},
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
        "official_loras": item.get("official_loras")
        or {"highres": {"enabled": False}, "turbo": {"enabled": False}, "colorfix": {"enabled": False}},
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
