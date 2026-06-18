from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from .config import (
    ANIMA_HIGHRES_LORA_NAME,
    ANIMA_MAPPING_PATH,
    ANIMA_TURBO_LORA_V01_NAME,
    ANIMA_TURBO_LORA_V02_NAME,
    ANIMA_WORKFLOW_PATH,
    COMFYUI_ANIMA_TEMPLATE_PATH,
    COMFYUI_LORA_DIRS,
)
from .model_info_cache import _object_choice
from .payload_builder import find_lora_file


def file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def workflow_source_diagnostics() -> dict[str, Any]:
    mapping = load_json_file(ANIMA_MAPPING_PATH)
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
        "source_sha256": source.get("source_sha256") or file_sha256(source_path),
        "source_modified_time": datetime.fromtimestamp(source_path.stat().st_mtime).isoformat(timespec="seconds") if source_path.exists() else "",
        "copied_workflow_sha256": file_sha256(ANIMA_WORKFLOW_PATH),
        "warning": warning,
    }


def mapping_diagnostics() -> dict[str, Any]:
    mapping = load_json_file(ANIMA_MAPPING_PATH)
    workflow = load_json_file(ANIMA_WORKFLOW_PATH)
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


def official_lora_diagnostics(info: dict[str, Any] | None = None) -> dict[str, Any]:
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
