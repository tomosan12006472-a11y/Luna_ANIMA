from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import quote
import uuid

from PIL import Image, ImageOps

from .config import USER_DATA_DIR
from .storage.json_store import JsonStore


SIGNATURE_DIR = USER_DATA_DIR / "signatures"
THUMB_DIR = SIGNATURE_DIR / "thumbs"
MANIFEST_PATH = SIGNATURE_DIR / "signatures.json"
MAX_SIGNATURE_SIDE = 4096
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
_MANIFEST_LOCK = RLock()

SIGNATURE_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty_manifest() -> dict[str, Any]:
    return {"schema_version": 1, "items": {}}


def _validate_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _empty_manifest()
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    data.setdefault("schema_version", 1)
    return data


def _manifest_store() -> JsonStore:
    return JsonStore(
        MANIFEST_PATH,
        default_factory=_empty_manifest,
        label="signature manifest",
        lock=_MANIFEST_LOCK,
        validator=_validate_manifest,
    )


def _load_manifest_unlocked() -> dict[str, Any]:
    return _manifest_store().read(strict=True)


def _save_manifest_unlocked(data: dict[str, Any]) -> None:
    _manifest_store().write(data)


def safe_name(name: str) -> str:
    stem = Path(name or "signature").stem or "signature"
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem)
    return cleaned[:64] or "signature"


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    signature_id = str(item.get("signature_id") or "")
    digest = str(item.get("sha256") or "")
    version = digest[:16] if digest else str(item.get("updated_at") or signature_id)
    query = f"?v={quote(version, safe='')}" if signature_id and version else ""
    safe = {
        key: item.get(key)
        for key in (
            "signature_id",
            "filename",
            "original_filename",
            "width",
            "height",
            "sha256",
            "created_at",
            "updated_at",
        )
    }
    safe["image_url"] = f"/api/signatures/{signature_id}/image{query}" if signature_id else ""
    safe["thumbnail_url"] = f"/api/signatures/{signature_id}/thumbnail{query}" if signature_id else ""
    return safe


def list_signatures() -> list[dict[str, Any]]:
    with _MANIFEST_LOCK:
        items = [_public_item(item) for item in _load_manifest_unlocked().get("items", {}).values() if isinstance(item, dict)]
    items.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return items


def get_signature(signature_id: str, *, public: bool = True) -> dict[str, Any] | None:
    with _MANIFEST_LOCK:
        item = _load_manifest_unlocked().get("items", {}).get(str(signature_id or ""))
    if not isinstance(item, dict):
        return None
    return _public_item(item) if public else dict(item)


def signature_image_path(signature_id: str) -> Path | None:
    item = get_signature(signature_id, public=False)
    if not item:
        return None
    path = Path(str(item.get("path") or ""))
    try:
        resolved = path.resolve()
        root = SIGNATURE_DIR.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root):
        return None
    return resolved if resolved.exists() else None


def signature_thumbnail_path(signature_id: str) -> Path | None:
    item = get_signature(signature_id, public=False)
    if not item:
        return None
    path = Path(str(item.get("thumbnail_path") or ""))
    try:
        resolved = path.resolve()
        root = THUMB_DIR.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root):
        return None
    return resolved if resolved.exists() else None


def _validate_upload(filename: str, data: bytes) -> str:
    if not data:
        raise ValueError("signature image is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("signature image is too large")
    ext = Path(filename or "signature.png").suffix.lower().lstrip(".") or "png"
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"unsupported signature image extension: {ext}")
    return ext


def save_signature_upload(filename: str, data: bytes) -> dict[str, Any]:
    _validate_upload(filename, data)
    digest = sha256(data).hexdigest()
    signature_id = f"sig_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    output_name = f"{signature_id}_{safe_name(filename)}.png"
    thumb_name = f"{signature_id}.png"
    image_path = SIGNATURE_DIR / output_name
    thumb_path = THUMB_DIR / thumb_name
    with Image.open(BytesIO(data)) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGBA")
        if max(image.size) > MAX_SIGNATURE_SIDE:
            image.thumbnail((MAX_SIGNATURE_SIDE, MAX_SIGNATURE_SIDE), Image.Resampling.LANCZOS)
        width, height = image.size
        image.save(image_path, "PNG", optimize=True)
        thumb = image.copy()
        thumb.thumbnail((512, 512), Image.Resampling.LANCZOS)
        thumb.save(thumb_path, "PNG", optimize=True)
    item = {
        "signature_id": signature_id,
        "filename": output_name,
        "original_filename": filename or "signature.png",
        "path": str(image_path),
        "thumbnail_path": str(thumb_path),
        "width": width,
        "height": height,
        "sha256": digest,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    with _MANIFEST_LOCK:
        manifest = _load_manifest_unlocked()
        manifest["items"][signature_id] = item
        _save_manifest_unlocked(manifest)
    return _public_item(item)


def delete_signature(signature_id: str) -> bool:
    with _MANIFEST_LOCK:
        manifest = _load_manifest_unlocked()
        item = manifest.get("items", {}).pop(str(signature_id or ""), None)
        if not isinstance(item, dict):
            return False
        _save_manifest_unlocked(manifest)
    for key in ("path", "thumbnail_path"):
        path = Path(str(item.get(key) or ""))
        try:
            resolved = path.resolve()
        except OSError:
            continue
        root = (THUMB_DIR if key == "thumbnail_path" else SIGNATURE_DIR).resolve()
        if resolved.is_relative_to(root) and resolved.exists():
            try:
                resolved.unlink()
            except OSError:
                pass
    return True
