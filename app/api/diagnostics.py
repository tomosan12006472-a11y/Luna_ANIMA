from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie

from .. import lora_catalog, reference_store
from ..anima_adapter import catalog, load_settings
from ..auth import require_auth
from ..capabilities import anima_shift_capability, comfy_visible_loras
from ..config import (
    ANIMA_MAPPING_PATH,
    ANIMA_WORKFLOW_PATH,
    CHARACTER_CATALOG_ROOT,
    COMFYUI_ADDR_DEFAULT,
    MOBILE_PAYLOAD_DIR,
    ROOT_DIR,
)
from ..diagnostics_helpers import (
    mapping_diagnostics,
    official_lora_diagnostics,
    workflow_source_diagnostics,
)
from ..face_detailer import face_detailer_capabilities
from ..generation_prepare import face_detailer_capability_payload, reference_capability_payload, reference_modules_availability_payload
from ..history_store import list_history
from ..model_info_cache import _object_choice, cached_object_info, model_cache_status as _model_cache_status

router = APIRouter()

@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "app": "Luna ANIMA",
        "character_catalog_root_exists": CHARACTER_CATALOG_ROOT.exists(),
        "catalog_count": len(catalog.wai),
        "custom_count": len(catalog.custom),
    }


@router.get("/api/diagnostics")
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
        "background_reference": (reference_modules_availability_payload(addr).get("reference_modules") or {}).get("background", {}),
        "face_detailer": face_detailer_capability_payload(addr).get("face_detailer", {}),
        "history_count": len(list_history(500)),
        "settings_path": str(ROOT_DIR / "user_data" / "settings.json"),
    }


@router.get("/api/diagnostics/full")
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
    official_loras = official_lora_diagnostics(info)
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
        "workflow_source": workflow_source_diagnostics(),
        "mapping": mapping_diagnostics(),
        "models": model_status,
        "anima_shift": shift_info,
        "reference_assist": reference_store.reference_capabilities(info or {}).get("reference_assist", {}) if info else reference_capability_payload(addr).get("reference_assist", {}),
        "background_reference": (reference_modules_availability_payload(addr).get("reference_modules") or {}).get("background", {}),
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
