from __future__ import annotations

from typing import Any

from .._shared_utils import normalize_lora_strengths
from ..config import (
    ANIMA_HIGHRES_LORA_NAME,
    ANIMA_TURBO_LORA_V01_NAME,
    ANIMA_TURBO_LORA_V02_NAME,
    COMFYUI_LORA_DIRS,
)
from .prompts import is_lora_sample_mode


def find_lora_file(name: str) -> str:
    for directory in COMFYUI_LORA_DIRS:
        path = directory / name
        if path.exists():
            return str(path)
    return ""


def comfy_lora_name(name: str) -> str:
    return name.replace("/", "\\")


def resolve_official_loras(request: dict[str, Any]) -> dict[str, Any]:
    if is_lora_sample_mode(request):
        return {
            "highres": {"enabled": False, "file": ANIMA_HIGHRES_LORA_NAME, "path": "", "strength": 0.0},
            "turbo": {
                "enabled": False,
                "file": ANIMA_TURBO_LORA_V02_NAME,
                "path": "",
                "version": "v0.2",
                "strength": 0.0,
                "preset_applied": False,
            },
        }
    official = request.get("official_loras") or {}
    highres = official.get("highres") if isinstance(official.get("highres"), dict) else {}
    turbo = official.get("turbo") if isinstance(official.get("turbo"), dict) else {}
    turbo_v02_path = find_lora_file(ANIMA_TURBO_LORA_V02_NAME)
    turbo_v01_path = find_lora_file(ANIMA_TURBO_LORA_V01_NAME)
    requested_version = str(turbo.get("version") or "auto")
    if requested_version == "v0.1":
        turbo_name = ANIMA_TURBO_LORA_V01_NAME
        turbo_path = turbo_v01_path
    elif requested_version == "v0.2":
        turbo_name = ANIMA_TURBO_LORA_V02_NAME
        turbo_path = turbo_v02_path
    else:
        turbo_name = ANIMA_TURBO_LORA_V02_NAME if turbo_v02_path else ANIMA_TURBO_LORA_V01_NAME
        turbo_path = turbo_v02_path or turbo_v01_path
    return {
        "highres": {
            "enabled": bool(highres.get("enabled")),
            "file": ANIMA_HIGHRES_LORA_NAME,
            "path": find_lora_file(ANIMA_HIGHRES_LORA_NAME),
            "strength": max(0.0, min(1.0, float(highres.get("strength") or 0.6))),
        },
        "turbo": {
            "enabled": bool(turbo.get("enabled")),
            "file": turbo_name,
            "path": turbo_path,
            "version": "v0.2" if turbo_name == ANIMA_TURBO_LORA_V02_NAME else "v0.1",
            "strength": max(0.0, min(1.0, float(turbo.get("strength") or 0.6))),
            "preset_applied": bool(turbo.get("preset_applied")),
        },
    }


def official_lora_summary(request: dict[str, Any]) -> dict[str, Any]:
    resolved = resolve_official_loras(request)
    return {
        "highres": {
            "enabled": resolved["highres"]["enabled"],
            "file": resolved["highres"]["file"] if resolved["highres"]["enabled"] else "",
            "found": bool(resolved["highres"]["path"]),
            "strength": resolved["highres"]["strength"],
        },
        "turbo": {
            "enabled": resolved["turbo"]["enabled"],
            "file": resolved["turbo"]["file"] if resolved["turbo"]["enabled"] else "",
            "found": bool(resolved["turbo"]["path"]),
            "version": resolved["turbo"]["version"],
            "strength": resolved["turbo"]["strength"],
            "preset_applied": resolved["turbo"]["preset_applied"],
        },
    }


def normalize_lora_application(value: Any) -> str:
    text = str(value or "model_clip").strip().lower()
    if text in {"off", "none", "disabled"}:
        return "off"
    if text in {"base", "model", "model_only"}:
        return "model_only"
    return "model_clip"


def apply_official_loras(workflow: dict[str, Any], request: dict[str, Any]) -> list[Any]:
    resolved = resolve_official_loras(request)
    previous_model: list[Any] = ["44", 0]
    next_node_id = 9001
    for key in ("highres", "turbo"):
        item = resolved[key]
        if not item["enabled"]:
            continue
        if not item["path"]:
            raise ValueError(f"Official ANIMA LoRA file is missing: {item['file']}")
        node_id = str(next_node_id)
        workflow[node_id] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": previous_model,
                "lora_name": item["file"],
                "strength_model": item["strength"],
            },
        }
        previous_model = [node_id, 0]
        next_node_id += 1
    workflow["46"]["inputs"]["model"] = previous_model
    return previous_model


def apply_catalog_loras(workflow: dict[str, Any], request: dict[str, Any], previous_model: list[Any]) -> list[Any]:
    next_node_id = 9051
    previous_clip: list[Any] = ["45", 0]
    for raw in request.get("loras", []) or []:
        if not isinstance(raw, dict):
            continue
        raw = normalize_lora_strengths(raw)
        application = normalize_lora_application(raw.get("application", raw.get("mode")))
        if raw.get("enabled") is False or application == "off":
            continue
        lora_name = str(raw.get("name") or raw.get("relative_path") or "").strip()
        if not lora_name:
            continue
        node_id = str(next_node_id)
        if application == "model_only":
            workflow[node_id] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": previous_model,
                    "lora_name": comfy_lora_name(lora_name),
                    "strength_model": raw["strength_model"],
                },
            }
            previous_model = [node_id, 0]
        else:
            workflow[node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": previous_model,
                    "clip": previous_clip,
                    "lora_name": comfy_lora_name(lora_name),
                    "strength_model": raw["strength_model"],
                    "strength_clip": raw["strength_clip"],
                },
            }
            previous_model = [node_id, 0]
            previous_clip = [node_id, 1]
        next_node_id += 1
    workflow["46"]["inputs"]["model"] = previous_model
    workflow["11"]["inputs"]["clip"] = previous_clip
    workflow["12"]["inputs"]["clip"] = previous_clip
    return previous_model
