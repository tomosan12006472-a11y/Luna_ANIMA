from __future__ import annotations

from typing import Any

from .config import COMFYUI_ADDR_DEFAULT
from .model_info_cache import _object_choice, cached_object_info
from .payload_builder import model_sampling_shift_metadata


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


def comfy_visible_loras(addr: str | None = None, refresh: bool = False) -> list[str]:
    try:
        info, _cache = cached_object_info(addr or COMFYUI_ADDR_DEFAULT, refresh=refresh)
    except Exception:
        return []
    loras = _object_choice(info, "LoraLoaderModelOnly", "lora_name")
    if not loras:
        loras = _object_choice(info, "LoraLoader", "lora_name")
    return loras
