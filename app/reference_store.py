from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from threading import Lock
import time
import uuid
from typing import Any

from PIL import Image, ImageOps

from ._shared_utils import write_json_atomic
from .config import ROOT_DIR


REFERENCE_DIR = ROOT_DIR / "user_data" / "reference_inputs"
THUMB_DIR = REFERENCE_DIR / "thumbs"
MANIFEST_PATH = REFERENCE_DIR / "reference_inputs.json"
MAX_REFERENCE_SIDE = 2048
_MANIFEST_LOCK = Lock()

REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clamp_float(value: Any, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def empty_manifest() -> dict[str, Any]:
    return {"schema_version": 1, "items": {}}


def load_manifest() -> dict[str, Any]:
    with _MANIFEST_LOCK:
        return _load_manifest_unlocked()


def _load_manifest_unlocked() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return empty_manifest()
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        time.sleep(0.05)
        try:
            data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception as second_error:
            raise RuntimeError("reference manifest is temporarily unreadable") from second_error
    if not isinstance(data, dict):
        return empty_manifest()
    items = data.get("items")
    if not isinstance(items, dict):
        data["items"] = {}
    data.setdefault("schema_version", 1)
    return data


def save_manifest(data: dict[str, Any]) -> None:
    with _MANIFEST_LOCK:
        _save_manifest_unlocked(data)


def _save_manifest_unlocked(data: dict[str, Any]) -> None:
    write_json_atomic(MANIFEST_PATH, data)


def public_item(item: dict[str, Any]) -> dict[str, Any]:
    image_id = str(item.get("image_id") or "")
    return {
        **item,
        "image_url": f"/api/reference/images/{image_id}/image" if image_id else "",
        "thumbnail_url": f"/api/reference/images/{image_id}/thumbnail" if image_id else "",
    }


def get_reference_image(image_id: str) -> dict[str, Any] | None:
    data = load_manifest()
    item = data.get("items", {}).get(image_id)
    return public_item(item) if isinstance(item, dict) else None


def list_reference_images(module: str | None = None) -> list[dict[str, Any]]:
    items = [public_item(item) for item in load_manifest().get("items", {}).values() if isinstance(item, dict)]
    if module:
        items = [item for item in items if str(item.get("module") or "general") == module]
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items


def safe_name(name: str) -> str:
    stem = Path(name or "reference").stem or "reference"
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem)
    return cleaned[:64] or "reference"


def save_reference_upload(filename: str, data: bytes, *, app_scope: str, module: str = "general") -> dict[str, Any]:
    if not data:
        raise ValueError("reference image is empty")
    digest = sha256(data).hexdigest()
    image_id = f"ref_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    output_name = f"{image_id}_{safe_name(filename)}.png"
    thumb_name = f"{image_id}.jpg"
    image_path = REFERENCE_DIR / output_name
    thumb_path = THUMB_DIR / thumb_name
    with Image.open(BytesIO(data)) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        image.thumbnail((MAX_REFERENCE_SIDE, MAX_REFERENCE_SIDE), Image.Resampling.LANCZOS)
        width, height = image.size
        image.save(image_path, "PNG", optimize=True)
        thumb = image.copy()
        thumb.thumbnail((512, 512), Image.Resampling.LANCZOS)
        thumb.save(thumb_path, "JPEG", quality=86)
    item = {
        "image_id": image_id,
        "app_scope": app_scope,
        "module": module or "general",
        "filename": output_name,
        "original_filename": filename or "reference.png",
        "path": str(image_path),
        "thumbnail_path": str(thumb_path),
        "width": width,
        "height": height,
        "sha256": digest,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "comfyui_image": {"name": None, "subfolder": "", "type": "input", "uploaded_at": None},
    }
    with _MANIFEST_LOCK:
        manifest = _load_manifest_unlocked()
        manifest["items"][image_id] = item
        _save_manifest_unlocked(manifest)
    return public_item(item)


def update_comfy_upload(image_id: str, upload_result: dict[str, Any]) -> dict[str, Any] | None:
    with _MANIFEST_LOCK:
        manifest = _load_manifest_unlocked()
        item = manifest.get("items", {}).get(image_id)
        if not isinstance(item, dict):
            return None
        parsed = upload_result.get("json") if isinstance(upload_result, dict) else {}
        if not isinstance(parsed, dict):
            parsed = {}
        item["comfyui_image"] = {
            "name": parsed.get("name") or item.get("filename"),
            "subfolder": parsed.get("subfolder") or "",
            "type": parsed.get("type") or "input",
            "uploaded_at": now_iso(),
        }
        item["updated_at"] = now_iso()
        manifest["items"][image_id] = item
        _save_manifest_unlocked(manifest)
        return public_item(item)


def delete_reference_image(image_id: str) -> bool:
    with _MANIFEST_LOCK:
        manifest = _load_manifest_unlocked()
        item = manifest.get("items", {}).pop(image_id, None)
        if not isinstance(item, dict):
            return False
        for key in ("path", "thumbnail_path"):
            path = Path(str(item.get(key) or ""))
            if path.exists() and REFERENCE_DIR in path.parents:
                path.unlink()
        _save_manifest_unlocked(manifest)
        return True


def object_choices(info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    value = info.get(class_name, {}).get("input", {}).get("required", {}).get(input_name, [[]])
    if isinstance(value, list) and value and isinstance(value[0], list):
        return [str(item) for item in value[0]]
    if isinstance(value, list) and len(value) > 1 and isinstance(value[1], dict) and isinstance(value[1].get("options"), list):
        return [str(item) for item in value[1]["options"]]
    return []


def reference_capabilities(info: dict[str, Any] | None, *, cache: dict[str, Any] | None = None) -> dict[str, Any]:
    info = info or {}
    node_names = set(info.keys())
    controlnet_models = object_choices(info, "ControlNetLoader", "control_net_name")
    control_apply = "ControlNetApplyAdvanced" if "ControlNetApplyAdvanced" in node_names else "ControlNetApply" if "ControlNetApply" in node_names else ""
    control_required = ["LoadImage", "ControlNetLoader"]
    if not control_apply:
        control_required.append("ControlNetApplyAdvanced")
    missing_control = [name for name in control_required if name not in node_names]
    if not controlnet_models:
        missing_control.append("controlnet_model")
    img2img_required = ["LoadImage", "VAEEncode", "VAEDecode", "KSampler"]
    missing_img2img = [name for name in img2img_required if name not in node_names]
    ip_nodes = sorted(name for name in node_names if "ipadapter" in name.lower() or "ip adapter" in name.lower())
    ip_missing = [] if ("LoadImage" in node_names and ip_nodes) else ["LoadImage", "IPAdapter"]
    modes = {
        "controlnet": {
            "supported": not missing_control,
            "apply_node_type": control_apply,
            "has_union_type": "SetUnionControlNetType" in node_names,
            "missing_nodes": missing_control,
            "available_nodes": [name for name in ["LoadImage", "ControlNetLoader", "ControlNetApplyAdvanced", "ControlNetApply", "SetUnionControlNetType"] if name in node_names],
        },
        "img2img_reference": {
            "supported": not missing_img2img,
            "missing_nodes": missing_img2img,
            "available_nodes": [name for name in img2img_required if name in node_names],
        },
        "ipadapter": {
            "supported": "LoadImage" in node_names and bool(ip_nodes),
            "missing_nodes": ip_missing,
            "available_nodes": ip_nodes[:20],
        },
    }
    preferred = "controlnet" if modes["controlnet"]["supported"] else "img2img_reference" if modes["img2img_reference"]["supported"] else "ipadapter" if modes["ipadapter"]["supported"] else None
    notes: list[str] = []
    if not preferred:
        notes.append("Reference Assist is disabled until required ComfyUI nodes are available.")
    elif preferred != "controlnet":
        notes.append(f"Preferred fallback is {preferred}; ControlNet is not fully available.")
    return {
        "reference_assist": {
            "supported": bool(preferred),
            "preferred_mode": preferred,
            "modes": modes,
            "controlnet_models": controlnet_models,
            "upload_supported": True,
            "object_info_node_count": len(node_names),
            "cache": cache or {},
            "notes": notes,
        }
    }


def sanitize_reference_assist(value: Any, *, app_scope: str, default_strength: float) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    mode = str(raw.get("mode") or "auto")
    if mode not in {"auto", "controlnet", "img2img_reference"}:
        mode = "auto"
    return {
        "enabled": bool(raw.get("enabled")),
        "mode": mode,
        "experimental": bool(raw.get("experimental")),
        "app_scope": app_scope,
        "image_id": str(raw.get("image_id") or ""),
        "image_name": str(raw.get("image_name") or ""),
        "controlnet_model": str(raw.get("controlnet_model") or ""),
        "strength": clamp_float(raw.get("strength"), default_strength),
        "start_percent": clamp_float(raw.get("start_percent"), 0.0),
        "end_percent": clamp_float(raw.get("end_percent"), 0.75),
        "resize_mode": str(raw.get("resize_mode") or "fit"),
        "union_type": str(raw.get("union_type") or "auto"),
        "comfyui_image": raw.get("comfyui_image") if isinstance(raw.get("comfyui_image"), dict) else {"name": None, "subfolder": "", "type": "input"},
    }
