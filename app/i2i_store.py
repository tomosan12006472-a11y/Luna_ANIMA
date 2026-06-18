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
from .schemas.reference import ImageToImageSettings


I2I_DIR = ROOT_DIR / "user_data" / "i2i_inputs"
THUMB_DIR = I2I_DIR / "thumbs"
PREPARED_DIR = I2I_DIR / "prepared"
MANIFEST_PATH = I2I_DIR / "i2i_inputs.json"
MAX_I2I_SIDE = 4096
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
_MANIFEST_LOCK = Lock()

I2I_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)
PREPARED_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clamp_float(value: Any, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _round_to_multiple(value: Any, multiple: int = 8) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = multiple
    return max(multiple, int(round(number / multiple) * multiple))


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
            raise RuntimeError("i2i manifest is temporarily unreadable") from second_error
    if not isinstance(data, dict):
        return empty_manifest()
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    data.setdefault("schema_version", 1)
    return data


def save_manifest(data: dict[str, Any]) -> None:
    with _MANIFEST_LOCK:
        _save_manifest_unlocked(data)


def _save_manifest_unlocked(data: dict[str, Any]) -> None:
    write_json_atomic(MANIFEST_PATH, data)


def safe_name(name: str) -> str:
    stem = Path(name or "i2i").stem or "i2i"
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem)
    return cleaned[:64] or "i2i"


def public_item(item: dict[str, Any]) -> dict[str, Any]:
    image_id = str(item.get("image_id") or "")
    return {
        **item,
        "image_url": f"/api/i2i/images/{image_id}/image" if image_id else "",
        "thumbnail_url": f"/api/i2i/images/{image_id}/thumbnail" if image_id else "",
    }


def get_i2i_image(image_id: str) -> dict[str, Any] | None:
    item = load_manifest().get("items", {}).get(str(image_id or ""))
    return public_item(item) if isinstance(item, dict) else None


def list_i2i_images(*, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    items = [public_item(item) for item in load_manifest().get("items", {}).values() if isinstance(item, dict)]
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    start = max(0, int(offset or 0))
    page_limit = max(1, min(100, int(limit or 50)))
    return items[start : start + page_limit]


def _validate_upload(filename: str, data: bytes) -> str:
    if not data:
        raise ValueError("i2i image is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("i2i image is too large")
    ext = Path(filename or "image.png").suffix.lower().lstrip(".") or "png"
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"unsupported i2i image extension: {ext}")
    return ext


def save_i2i_upload(filename: str, data: bytes, *, app_scope: str, source: str = "upload", source_history_id: str | None = None) -> dict[str, Any]:
    _validate_upload(filename, data)
    digest = sha256(data).hexdigest()
    image_id = f"i2i_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    output_name = f"{image_id}_{safe_name(filename)}.png"
    thumb_name = f"{image_id}.jpg"
    image_path = I2I_DIR / output_name
    thumb_path = THUMB_DIR / thumb_name
    with Image.open(BytesIO(data)) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        if max(image.size) > MAX_I2I_SIDE:
            image.thumbnail((MAX_I2I_SIDE, MAX_I2I_SIDE), Image.Resampling.LANCZOS)
        width, height = image.size
        image.save(image_path, "PNG", optimize=True)
        thumb = image.copy()
        thumb.thumbnail((512, 512), Image.Resampling.LANCZOS)
        thumb.save(thumb_path, "JPEG", quality=86)
    item = {
        "image_id": image_id,
        "app_scope": app_scope,
        "filename": output_name,
        "original_filename": filename or "i2i.png",
        "source": source,
        "source_history_id": source_history_id,
        "path": str(image_path),
        "thumbnail_path": str(thumb_path),
        "width": width,
        "height": height,
        "sha256": digest,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "prepared": {},
        "comfyui_image": {"name": None, "subfolder": "", "type": "input", "uploaded_at": None},
    }
    with _MANIFEST_LOCK:
        manifest = _load_manifest_unlocked()
        manifest["items"][image_id] = item
        _save_manifest_unlocked(manifest)
    return public_item(item)


def save_i2i_from_path(path: Path, *, app_scope: str, source_history_id: str) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise ValueError("source history image not found")
    return save_i2i_upload(path.name, path.read_bytes(), app_scope=app_scope, source="history", source_history_id=source_history_id)


def prepare_i2i_image(image_id: str, *, width: int, height: int, resize_mode: str = "fit", use_source_size: bool = False) -> dict[str, Any]:
    with _MANIFEST_LOCK:
        manifest = _load_manifest_unlocked()
        item = manifest.get("items", {}).get(str(image_id or ""))
        if not isinstance(item, dict):
            raise ValueError("i2i image not found")
        image_path = Path(str(item.get("path") or ""))
        if not image_path.exists():
            raise ValueError("i2i image file not found")
        source_width = int(item.get("width") or 0)
        source_height = int(item.get("height") or 0)
        target_width = _round_to_multiple(source_width if use_source_size else width)
        target_height = _round_to_multiple(source_height if use_source_size else height)
        resize_mode = str(resize_mode or "fit").lower()
        if resize_mode not in {"fit", "cover", "stretch"}:
            resize_mode = "fit"
        key = f"{target_width}x{target_height}_{resize_mode}"
        prepared = item.setdefault("prepared", {})
        existing = prepared.get(key) if isinstance(prepared.get(key), dict) else {}
        prepared_path = Path(str(existing.get("path") or ""))
        if not prepared_path.is_file():
            prepared_name = f"{item['image_id']}_{key}.png"
            prepared_path = PREPARED_DIR / prepared_name
            with Image.open(image_path) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
                if resize_mode == "stretch":
                    output = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
                elif resize_mode == "cover":
                    output = ImageOps.fit(image, (target_width, target_height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                else:
                    output = ImageOps.pad(image, (target_width, target_height), method=Image.Resampling.LANCZOS, color=(0, 0, 0), centering=(0.5, 0.5))
                output.save(prepared_path, "PNG", optimize=True)
            existing = {
                "filename": prepared_name,
                "path": str(prepared_path),
                "width": target_width,
                "height": target_height,
                "resize_mode": resize_mode,
                "created_at": now_iso(),
                "comfyui_image": {"name": None, "subfolder": "", "type": "input", "uploaded_at": None},
            }
            prepared[key] = existing
            item["updated_at"] = now_iso()
            manifest["items"][item["image_id"]] = item
            _save_manifest_unlocked(manifest)
        return {
            **public_item(item),
            "prepared_key": key,
            "prepared": existing,
            "prepared_path": str(prepared_path),
            "prepared_filename": existing.get("filename") or prepared_path.name,
            "prepared_width": target_width,
            "prepared_height": target_height,
            "source_width": source_width,
            "source_height": source_height,
            "resize_mode": resize_mode,
        }


def update_prepared_comfy_upload(image_id: str, prepared_key: str, upload_result: dict[str, Any]) -> dict[str, Any] | None:
    with _MANIFEST_LOCK:
        manifest = _load_manifest_unlocked()
        item = manifest.get("items", {}).get(str(image_id or ""))
        if not isinstance(item, dict):
            return None
        prepared = item.get("prepared") if isinstance(item.get("prepared"), dict) else {}
        entry = prepared.get(prepared_key) if isinstance(prepared.get(prepared_key), dict) else None
        if entry is None:
            return None
        parsed = upload_result.get("json") if isinstance(upload_result, dict) else {}
        if not isinstance(parsed, dict):
            parsed = {}
        entry["comfyui_image"] = {
            "name": parsed.get("name") or entry.get("filename"),
            "subfolder": parsed.get("subfolder") or "",
            "type": parsed.get("type") or "input",
            "uploaded_at": now_iso(),
        }
        entry["updated_at"] = now_iso()
        prepared[prepared_key] = entry
        item["prepared"] = prepared
        item["updated_at"] = now_iso()
        manifest["items"][item["image_id"]] = item
        _save_manifest_unlocked(manifest)
        return public_item(item)


def delete_i2i_image(image_id: str) -> bool:
    with _MANIFEST_LOCK:
        manifest = _load_manifest_unlocked()
        item = manifest.get("items", {}).pop(str(image_id or ""), None)
        if not isinstance(item, dict):
            return False
        for key in ("path", "thumbnail_path"):
            path = Path(str(item.get(key) or ""))
            if path.exists() and I2I_DIR in path.parents:
                path.unlink()
        prepared = item.get("prepared") if isinstance(item.get("prepared"), dict) else {}
        for entry in prepared.values():
            path = Path(str((entry or {}).get("path") or ""))
            if path.exists() and I2I_DIR in path.parents:
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


def i2i_capabilities(info: dict[str, Any] | None, *, cache: dict[str, Any] | None = None) -> dict[str, Any]:
    info = info or {}
    node_names = set(info.keys())
    required = ["LoadImage", "KSampler"]
    if "VAEEncode" not in node_names and "VAEEncodeTiled" not in node_names:
        required.append("VAEEncode")
    missing = [name for name in required if name not in node_names]
    return {
        "image_to_image": {
            "supported": not missing,
            "nodes": {
                "LoadImage": "LoadImage" in node_names,
                "VAEEncode": "VAEEncode" in node_names,
                "VAEEncodeTiled": "VAEEncodeTiled" in node_names,
                "KSampler": "KSampler" in node_names,
                "KSamplerAdvanced": "KSamplerAdvanced" in node_names,
                "ImageScale": "ImageScale" in node_names,
            },
            "limits": {
                "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
                "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
            },
            "missing_nodes": missing,
            "upload_supported": True,
            "cache": cache or {},
            "warnings": [] if not missing else ["Image to Image is disabled until required ComfyUI nodes are available."],
        }
    }


def sanitize_image_to_image(value: Any, *, app_scope: str) -> dict[str, Any]:
    raw = value.model_dump() if hasattr(value, "model_dump") else value if isinstance(value, dict) else {}
    return ImageToImageSettings.model_validate({**raw, "app_scope": app_scope}).model_dump()
