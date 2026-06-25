from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import base64
import hashlib
import json
from pathlib import Path
import shutil
from threading import Lock, RLock
import time
import uuid
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .anima_adapter import catalog
from .config import HISTORY_DIR, IMAGE_DIR, PUBLIC_DIR, THUMBNAIL_DIR
from .output_organizer import infer_anima_generation_method, organization_metadata
from .payload_builder import compute_hires_size, official_lora_summary
from .storage.json_store import JsonStore, JsonStoreReadError

ACTIVE_STATUSES = {"queued", "running", "stale", "missing"}
PENDING_STATUSES = {"queued", "running", "stale", "missing"}
VISIBLE_WITHOUT_IMAGE_STATUSES = ACTIVE_STATUSES | {"failed"}
MISSING_AFTER = timedelta(minutes=2)
STALE_AFTER = timedelta(hours=6)
SMALL_THUMBNAIL_DIR = THUMBNAIL_DIR.parent / "thumbnails_small"
SMALL_THUMBNAIL_SIZE = (320, 320)
SMALL_THUMBNAIL_QUALITY = 76
_HISTORY_LIST_CACHE_LOCK = Lock()
_HISTORY_LIST_CACHE_SIGNATURE: str | None = None
_HISTORY_LIST_CACHE_ITEMS: list[dict[str, Any]] = []
_HISTORY_LIST_CACHE_WARNINGS: list[str] = []
_HISTORY_ITEM_LOCKS_LOCK = Lock()
_HISTORY_ITEM_LOCKS: dict[str, RLock] = {}

SMALL_THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def history_path(history_id: str) -> Path:
    return HISTORY_DIR / f"{history_id}.json"


def small_thumbnail_path(history_id: str) -> Path:
    return SMALL_THUMBNAIL_DIR / f"{history_id}.jpg"


def _history_item_lock(history_id: Any) -> RLock:
    key = str(history_id or "")
    with _HISTORY_ITEM_LOCKS_LOCK:
        lock = _HISTORY_ITEM_LOCKS.get(key)
        if lock is None:
            lock = RLock()
            _HISTORY_ITEM_LOCKS[key] = lock
        return lock


@contextmanager
def _locked_history_item(history_id: Any):
    lock = _history_item_lock(history_id)
    with lock:
        yield


def _validate_history_item_json(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("history item must be a JSON object")
    return data


def _history_item_store_for_path(path: Path) -> JsonStore:
    return JsonStore(
        path,
        default_factory=lambda: None,
        label=f"history item {path.stem}",
        lock=_history_item_lock(path.stem),
        validator=_validate_history_item_json,
    )


def _history_item_store(history_id: str) -> JsonStore:
    return _history_item_store_for_path(history_path(history_id))


def load_history_item(history_id: str, *, strict: bool = False) -> dict[str, Any] | None:
    store = _history_item_store(history_id)
    if not store.path.exists():
        return None
    item = store.read(strict=strict)
    if item is None:
        return None
    return normalize_history_item(item)


def _history_character_catalog_entry(char: dict[str, Any]) -> Any:
    prompt_tag = str(char.get("prompt_tag") or "").strip()
    source = str(char.get("source") or "")
    role = str(char.get("role") or "")
    kind = str(char.get("kind") or "")
    value = str(char.get("id") or char.get("display_name") or char.get("name") or "").strip()
    is_original = source == "original_character" or role == "original" or kind == "original"
    if is_original:
        entry = catalog.original_by_id.get(value) or catalog.original_by_display.get(value)
        if not entry and prompt_tag:
            entry = next((candidate for candidate in catalog.original if candidate.prompt_tag == prompt_tag), None)
        return entry
    if prompt_tag:
        entry = catalog.by_prompt.get(prompt_tag)
        if entry:
            return entry
    return catalog.by_display.get(value) or catalog.by_prompt.get(value)


def normalize_history_characters(item: dict[str, Any]) -> None:
    characters = item.get("characters")
    if not isinstance(characters, list):
        return
    normalized: list[Any] = []
    names: list[str] = []
    for char in characters:
        if not isinstance(char, dict):
            normalized.append(char)
            text = str(char or "").strip()
            if text:
                names.append(text)
            continue
        data = dict(char)
        original_display = str(data.get("display_name_original") or data.get("display_name") or data.get("name") or data.get("id") or "").strip()
        entry = _history_character_catalog_entry(data)
        if entry:
            data.setdefault("display_name_original", original_display)
            data["display_name"] = entry.display_name
            data["name"] = entry.display_name
            data["display_name_ja"] = entry.display_name
            data["prompt_tag"] = data.get("prompt_tag") or entry.prompt_tag
            data.setdefault("prompt_safe_name", "")
        normalized.append(data)
        display = str(data.get("display_name_ja") or data.get("display_name") or data.get("name") or "").strip()
        if display:
            names.append(display)
    item["characters"] = normalized
    if names:
        item["character_names"] = names


def normalize_history_item(item: dict[str, Any]) -> dict[str, Any]:
    history_id = str(item.get("id") or "")
    image_path = Path(str(item.get("image_path") or ""))
    thumb_path = Path(str(item.get("thumbnail_path") or ""))
    has_images = bool(item.get("image_path") and item.get("thumbnail_path") and image_path.exists() and thumb_path.exists())
    item["status"] = str(item.get("status") or ("completed" if has_images else "queued"))
    normalize_history_characters(item)
    if history_id:
        item["image_url"] = f"/api/history/{history_id}/image" if has_images else None
        item["thumbnail_url"] = f"/api/history/{history_id}/thumbnail" if has_images else None
        item["thumbnail_small_url"] = f"/api/history/{history_id}/thumbnail-small" if has_images else None
        if item.get("public_save", {}).get("saved"):
            item["public_image_url"] = f"/api/history/{history_id}/public-image"
    return item


def save_history_item(item: dict[str, Any]) -> None:
    history_id = str(item["id"])
    _history_item_store(history_id).write(_validate_history_item_json(item))


def _history_directory_signature() -> tuple[str, list[Path]]:
    entries: list[tuple[str, int, int, Path]] = []
    for path in HISTORY_DIR.glob("*.json"):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((path.name, int(stat.st_mtime_ns), int(stat.st_size), path))
    entries.sort(key=lambda entry: entry[0])
    signature_payload = [(name, mtime_ns, size) for name, mtime_ns, size, _path in entries]
    signature = hashlib.sha256(json.dumps(signature_payload, separators=(",", ":")).encode("utf-8")).hexdigest()
    return signature, [path for _name, _mtime_ns, _size, path in entries]


def history_collection_revision() -> str:
    signature, _ = _history_directory_signature()
    return signature


def _load_visible_history_from_paths(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in paths:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            time.sleep(0.05)
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                warnings.append(f"Skipped broken history entry: {path.name}")
                continue
        if not isinstance(item, dict):
            warnings.append(f"Skipped invalid history entry: {path.name}")
            continue
        status = str(item.get("status") or "").lower()
        image_path = Path(str(item.get("image_path") or ""))
        thumb_path = Path(str(item.get("thumbnail_path") or ""))
        has_images = bool(item.get("image_path") and item.get("thumbnail_path") and image_path.exists() and thumb_path.exists())
        if not has_images and status not in VISIBLE_WITHOUT_IMAGE_STATUSES:
            warnings.append(f"Skipped missing image history entry: {path.name}")
            continue
        items.append(normalize_history_item(item))
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items, warnings


def _cached_visible_history_with_warnings() -> tuple[list[dict[str, Any]], list[str]]:
    global _HISTORY_LIST_CACHE_ITEMS, _HISTORY_LIST_CACHE_SIGNATURE, _HISTORY_LIST_CACHE_WARNINGS
    signature, paths = _history_directory_signature()
    with _HISTORY_LIST_CACHE_LOCK:
        if _HISTORY_LIST_CACHE_SIGNATURE == signature:
            return [dict(item) for item in _HISTORY_LIST_CACHE_ITEMS], list(_HISTORY_LIST_CACHE_WARNINGS)
        items, warnings = _load_visible_history_from_paths(paths)
        _HISTORY_LIST_CACHE_SIGNATURE = signature
        _HISTORY_LIST_CACHE_ITEMS = [dict(item) for item in items]
        _HISTORY_LIST_CACHE_WARNINGS = list(warnings)
        return [dict(item) for item in _HISTORY_LIST_CACHE_ITEMS], list(_HISTORY_LIST_CACHE_WARNINGS)


def _reset_history_cache_for_tests() -> None:
    global _HISTORY_LIST_CACHE_ITEMS, _HISTORY_LIST_CACHE_SIGNATURE, _HISTORY_LIST_CACHE_WARNINGS
    with _HISTORY_LIST_CACHE_LOCK:
        _HISTORY_LIST_CACHE_SIGNATURE = None
        _HISTORY_LIST_CACHE_ITEMS = []
        _HISTORY_LIST_CACHE_WARNINGS = []


def list_history(limit: int = 100) -> list[dict[str, Any]]:
    return list_history_with_warnings(limit)[0]


def _all_visible_history_with_warnings() -> tuple[list[dict[str, Any]], list[str]]:
    items, warnings = _cached_visible_history_with_warnings()
    return items, warnings


def list_history_with_warnings(limit: int = 100) -> tuple[list[dict[str, Any]], list[str]]:
    items, warnings = _all_visible_history_with_warnings()
    return items[: max(1, min(limit, 500))], warnings


def list_all_history_with_warnings() -> tuple[list[dict[str, Any]], list[str]]:
    return _all_visible_history_with_warnings()


def list_history_page(limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], list[str], dict[str, int], int]:
    items, warnings = _all_visible_history_with_warnings()
    start = max(0, int(offset or 0))
    page_limit = max(1, min(int(limit or 20), 100))
    return items[start : start + page_limit], warnings, summarize_history(items), len(items)


def summarize_history(items: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"queued": 0, "running": 0, "completed": 0, "failed": 0, "stale": 0, "missing": 0}
    for item in items:
        status = str(item.get("status") or "completed")
        if status in summary:
            summary[status] += 1
        else:
            summary["completed"] += 1
    summary["active"] = summary["queued"] + summary["running"]
    return summary


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _model_short(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return Path(text.replace("\\", "/")).stem or text


def _prompt_excerpt(item: dict[str, Any], limit: int = 120) -> str:
    text = _first_text(
        item.get("positive"),
        item.get("prompt"),
        item.get("natural_description"),
        item.get("common"),
        item.get("negative"),
        item.get("prompt_excerpt"),
    )
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _character_summary(item: dict[str, Any]) -> str:
    names = item.get("character_names")
    if isinstance(names, list):
        joined = ", ".join(str(name).strip() for name in names if str(name).strip())
        if joined:
            return joined
    chars = item.get("characters")
    if isinstance(chars, list):
        parts: list[str] = []
        for char in chars:
            if isinstance(char, dict):
                text = _first_text(char.get("display_name"), char.get("name"), char.get("id"), char.get("slot"))
            else:
                text = str(char or "").strip()
            if text:
                parts.append(text)
        if parts:
            return ", ".join(parts)
    return _first_text(item.get("original_character"), item.get("character_summary"))


def lite_history_item(item: dict[str, Any]) -> dict[str, Any]:
    """Return only fields needed by the history grid."""
    history_id = str(item.get("id") or "")
    flags = dict(item.get("flags") or {})
    thumbnail_small_url = item.get("thumbnail_small_url") or (f"/api/history/{history_id}/thumbnail-small" if history_id and item.get("thumbnail_url") else None)
    thumbnail_url = thumbnail_small_url or item.get("thumbnail_url")
    model_sampling = dict(item.get("model_sampling") or {})
    shift = item.get("shift", model_sampling.get("shift"))
    return {
        "id": history_id,
        "created_at": item.get("created_at"),
        "status": item.get("status"),
        "thumbnail_url": thumbnail_url,
        "thumbnail_small_url": thumbnail_small_url,
        "width": item.get("width"),
        "height": item.get("height"),
        "output_width": item.get("output_width"),
        "output_height": item.get("output_height"),
        "seed": item.get("seed"),
        "model": item.get("model"),
        "text_encoder": item.get("text_encoder"),
        "vae": item.get("vae"),
        "model_short": item.get("model_short") or _model_short(item.get("model")),
        "sampler": item.get("sampler"),
        "scheduler": item.get("scheduler"),
        "rating": item.get("rating"),
        "shift": shift,
        "flags": flags,
        "prompt_excerpt": _prompt_excerpt(item),
        "character_summary": _character_summary(item),
        "filename": item.get("filename"),
        "prompt_id": item.get("prompt_id"),
        "hires_fix": {
            "enabled": bool((item.get("hires_fix") or {}).get("enabled")),
            "mode": (item.get("hires_fix") or {}).get("mode"),
        },
        "face_detailer": {
            "enabled": bool((item.get("face_detailer") or {}).get("enabled")),
            "mode": (item.get("face_detailer") or {}).get("mode"),
        },
        "hand_detailer": {
            "enabled": bool((item.get("hand_detailer") or {}).get("enabled")),
            "mode": (item.get("hand_detailer") or {}).get("mode"),
        },
        "operation": item.get("operation"),
        "parent_history_id": item.get("parent_history_id"),
    }


def is_pending_item(item: dict[str, Any]) -> bool:
    return str(item.get("status") or "") in PENDING_STATUSES and bool(item.get("prompt_id"))


def pending_age_is_stale(item: dict[str, Any]) -> bool:
    return pending_age_exceeds(item, STALE_AFTER)


def pending_age_is_missing(item: dict[str, Any]) -> bool:
    return pending_age_exceeds(item, MISSING_AFTER)


def pending_age_exceeds(item: dict[str, Any], age: timedelta) -> bool:
    created_at = str(item.get("created_at") or "")
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return False
    return datetime.now(created.tzinfo) - created > age


def _extension_from_data_url(data_url: str) -> str:
    header = data_url.split(",", 1)[0].lower()
    if "jpeg" in header or "jpg" in header:
        return ".jpg"
    if "webp" in header:
        return ".webp"
    return ".png"


def image_bytes_from_data_url(data_url: str) -> bytes:
    if "," not in data_url:
        raise ValueError("invalid data URL")
    return base64.b64decode(data_url.split(",", 1)[1])


def save_generated_image(data_url: str, history_id: str) -> tuple[Path, Path]:
    ext = _extension_from_data_url(data_url)
    image_path = IMAGE_DIR / f"{history_id}{ext}"
    image_path.write_bytes(image_bytes_from_data_url(data_url))
    thumb_path = THUMBNAIL_DIR / f"{history_id}.jpg"
    small_path = small_thumbnail_path(history_id)
    with Image.open(image_path) as image:
        thumbnail = image.copy()
        thumbnail.thumbnail((512, 512))
        thumbnail.convert("RGB").save(thumb_path, "JPEG", quality=86)
        small = image.copy()
        small.thumbnail(SMALL_THUMBNAIL_SIZE)
        small.convert("RGB").save(small_path, "JPEG", quality=SMALL_THUMBNAIL_QUALITY, optimize=True)
    return image_path, thumb_path


def ensure_small_thumbnail(item: dict[str, Any]) -> Path | None:
    history_id = str(item.get("id") or "")
    image_path = Path(str(item.get("image_path") or ""))
    if not history_id or not image_path.exists():
        return None
    path = small_thumbnail_path(history_id)
    if path.exists():
        return path
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with Image.open(image_path) as image:
            image.thumbnail(SMALL_THUMBNAIL_SIZE)
            image.convert("RGB").save(tmp_path, "JPEG", quality=SMALL_THUMBNAIL_QUALITY, optimize=True)
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return None
    return path if path.exists() else None


def _prompt_random_collect_summary(request_data: dict[str, Any]) -> dict[str, Any] | None:
    data = request_data.get("prompt_random_collect")
    if not isinstance(data, dict) or not data.get("enabled"):
        return None
    generated_item = data.get("generated_item") if isinstance(data.get("generated_item"), dict) else {}
    generated_tags = str(data.get("generated_tags") or generated_item.get("tags") or "").strip()
    summary: dict[str, Any] = {
        "enabled": True,
        "mode": str(data.get("mode") or "random"),
        "instruction": str(data.get("instruction") or ""),
        "strength": str(data.get("strength") or ""),
        "include_characters": data.get("include_characters", True) is not False,
        "use_character_motifs": bool(
            data.get("include_characters", True) is not False and data.get("use_character_motifs", True)
        ),
        "generated_tags": generated_tags,
    }
    if generated_item:
        summary["generated_item"] = generated_item
    if isinstance(data.get("provider"), dict):
        summary["provider"] = data.get("provider")
    if isinstance(data.get("generation_strategy"), dict):
        summary["generation_strategy"] = data.get("generation_strategy")
    return summary


def enrich_history_item_from_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload_path = Path(str(item.get("payload_path") or ""))
    if not payload_path.exists():
        return item
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except Exception:
        return item
    if not isinstance(payload, dict):
        return item
    request_data = payload.get("request") if isinstance(payload.get("request"), dict) else payload
    raw_positive = str(request_data.get("positive_prompt") or payload.get("positive_prompt") or "").strip()
    if raw_positive and not str(item.get("positive_prompt") or "").strip():
        item["positive_prompt"] = raw_positive
    raw_negative = str(
        request_data.get("negative_prompt_raw")
        or request_data.get("negative_prompt")
        or payload.get("negative_prompt_raw")
        or payload.get("negative_prompt")
        or ""
    ).strip()
    if raw_negative and not str(item.get("negative_prompt_raw") or "").strip():
        item["negative_prompt_raw"] = raw_negative
    prompt_random_collect = _prompt_random_collect_summary(request_data)
    if prompt_random_collect and not isinstance(item.get("prompt_random_collect"), dict):
        item["prompt_random_collect"] = prompt_random_collect
    preset = str(request_data.get("official_lora_preset") or "").strip()
    if preset and not str(item.get("official_lora_preset") or "").strip():
        item["official_lora_preset"] = preset
    return item


def create_history_item(
    *,
    request_data: dict[str, Any],
    prompts: dict[str, Any],
    result: Any,
    payload_path: Path,
    workflow_mode: str,
) -> dict[str, Any] | None:
    if not getattr(result, "image_data_url", None):
        return None
    history_id = f"anima_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    image_path, thumb_path = save_generated_image(result.image_data_url, history_id)
    hires_fix = dict(request_data.get("hires_fix") or {"enabled": False})
    size = compute_hires_size(request_data)
    if hires_fix.get("enabled"):
        hires_fix.update(
            {
                "factor": size["factor"],
                "final_width": size["final_width"],
                "final_height": size["final_height"],
            }
        )
    output_method = infer_anima_generation_method(request_data)
    prompt_random_collect = _prompt_random_collect_summary(request_data)
    item = {
        "id": history_id,
        "created_at": now_iso(),
        "source": "anima_mobile",
        "image_path": str(image_path),
        "thumbnail_path": str(thumb_path),
        "filename": image_path.name,
        "model": request_data.get("model", "Default"),
        "text_encoder": request_data.get("text_encoder"),
        "vae": request_data.get("vae"),
        "width": request_data.get("width"),
        "height": request_data.get("height"),
        "output_width": size["final_width"],
        "output_height": size["final_height"],
        "seed": prompts.get("seed", request_data.get("seed")),
        "steps": request_data.get("steps"),
        "cfg": request_data.get("cfg"),
        "shift": request_data.get("shift"),
        "model_sampling": request_data.get("model_sampling", {}),
        "sampler": request_data.get("sampler"),
        "scheduler": request_data.get("scheduler"),
        "characters": prompts.get("character_metadata") or prompts.get("characters", []),
        "character_names": prompts.get("characters", []),
        "original_character": request_data.get("original_character") if request_data.get("original_character") != "None" else None,
        "positive": prompts.get("positive", ""),
        "positive_prompt": request_data.get("positive_prompt", ""),
        "negative": prompts.get("negative", request_data.get("negative_prompt", "")),
        "negative_prompt_raw": request_data.get("negative_prompt_raw", request_data.get("negative_prompt", "")),
        **({"dynamic_prompt": prompts.get("dynamic_prompt")} if prompts.get("dynamic_prompt") else {}),
        "negative_mode": prompts.get("negative_mode", request_data.get("negative_prompt_mode", "append")),
        "negative_preset": prompts.get("negative_preset", request_data.get("negative_preset", "")),
        "common": request_data.get("common_prompt", ""),
        "rating": prompts.get("rating", request_data.get("rating", "safe")),
        "rating_prompt_overrides": request_data.get("rating_prompt_overrides", {}),
        "quality_preset": request_data.get("quality_preset", "standard"),
        "quality_prompt_overrides": request_data.get("quality_prompt_overrides", {}),
        "natural_description": prompts.get("natural_description", request_data.get("natural_description", "")),
        "loras": request_data.get("loras", []),
        "workflow_mode": workflow_mode,
        "payload_path": str(payload_path),
        "prompt_id": getattr(result, "prompt_id", None),
        "hires_fix": hires_fix,
        "official_loras": official_lora_summary(request_data),
        "official_lora_preset": request_data.get("official_lora_preset", "off"),
        **({"prompt_random_collect": prompt_random_collect} if prompt_random_collect else {}),
        "reference_assist": request_data.get("reference_assist", {"enabled": False}),
        **({"reference_modules": request_data.get("reference_modules")} if isinstance(request_data.get("reference_modules"), dict) and any(isinstance(value, dict) and value.get("enabled") for value in (request_data.get("reference_modules") or {}).values()) else {}),
        **({"image_to_image": request_data.get("image_to_image")} if isinstance(request_data.get("image_to_image"), dict) and (request_data.get("image_to_image") or {}).get("enabled") else {}),
        **({"face_detailer": request_data.get("face_detailer")} if isinstance(request_data.get("face_detailer"), dict) and (request_data.get("face_detailer") or {}).get("enabled") else {}),
        **({"hand_detailer": request_data.get("hand_detailer")} if isinstance(request_data.get("hand_detailer"), dict) and (request_data.get("hand_detailer") or {}).get("enabled") else {}),
        **({"operation": request_data.get("operation")} if request_data.get("operation") else {}),
        **({"parent_history_id": request_data.get("parent_history_id")} if request_data.get("parent_history_id") else {}),
        **({"source_image": request_data.get("source_image")} if isinstance(request_data.get("source_image"), dict) else {}),
        "output_organization": organization_metadata(
            panel_id="anima",
            generation_method=output_method,
            original_prefix="Anima",
        ),
        "watermark": {"applied": False},
        "public_save": {"saved": False},
    }
    save_history_item(item)
    return item


def _hires_fix_summary(request_data: dict[str, Any]) -> dict[str, Any]:
    hires_fix = dict(request_data.get("hires_fix") or {"enabled": False})
    size = compute_hires_size(request_data)
    if hires_fix.get("enabled"):
        hires_fix.update(
            {
                "factor": size["factor"],
                "final_width": size["final_width"],
                "final_height": size["final_height"],
            }
        )
    return hires_fix


def create_pending_history_item(
    *,
    request_data: dict[str, Any],
    prompts: dict[str, Any],
    prompt_id: str,
    payload_path: Path,
    workflow_mode: str,
    index: int,
) -> dict[str, Any]:
    history_id = f"anima_pending_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    now = now_iso()
    size = compute_hires_size(request_data)
    output_method = infer_anima_generation_method(request_data)
    prompt_random_collect = _prompt_random_collect_summary(request_data)
    item = {
        "id": history_id,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "source": "anima_mobile",
        "image_path": None,
        "thumbnail_path": None,
        "filename": None,
        "model": request_data.get("model", "Default"),
        "text_encoder": request_data.get("text_encoder"),
        "vae": request_data.get("vae"),
        "width": request_data.get("width"),
        "height": request_data.get("height"),
        "output_width": size["final_width"],
        "output_height": size["final_height"],
        "seed": prompts.get("seed", request_data.get("seed")),
        "index": index,
        "steps": request_data.get("steps"),
        "cfg": request_data.get("cfg"),
        "shift": request_data.get("shift"),
        "model_sampling": request_data.get("model_sampling", {}),
        "sampler": request_data.get("sampler"),
        "scheduler": request_data.get("scheduler"),
        "characters": prompts.get("character_metadata") or prompts.get("characters", []),
        "character_names": prompts.get("characters", []),
        "original_character": request_data.get("original_character") if request_data.get("original_character") != "None" else None,
        "positive": prompts.get("positive", ""),
        "positive_prompt": request_data.get("positive_prompt", ""),
        "negative": prompts.get("negative", request_data.get("negative_prompt", "")),
        "negative_prompt_raw": request_data.get("negative_prompt_raw", request_data.get("negative_prompt", "")),
        **({"dynamic_prompt": prompts.get("dynamic_prompt")} if prompts.get("dynamic_prompt") else {}),
        "negative_mode": prompts.get("negative_mode", request_data.get("negative_prompt_mode", "append")),
        "negative_preset": prompts.get("negative_preset", request_data.get("negative_preset", "")),
        "common": request_data.get("common_prompt", ""),
        "rating": prompts.get("rating", request_data.get("rating", "safe")),
        "rating_prompt_overrides": request_data.get("rating_prompt_overrides", {}),
        "quality_preset": request_data.get("quality_preset", "standard"),
        "quality_prompt_overrides": request_data.get("quality_prompt_overrides", {}),
        "natural_description": prompts.get("natural_description", request_data.get("natural_description", "")),
        "loras": request_data.get("loras", []),
        "workflow_mode": workflow_mode,
        "payload_path": str(payload_path),
        "prompt_id": prompt_id,
        "hires_fix": _hires_fix_summary(request_data),
        "official_loras": official_lora_summary(request_data),
        "official_lora_preset": request_data.get("official_lora_preset", "off"),
        **({"prompt_random_collect": prompt_random_collect} if prompt_random_collect else {}),
        "reference_assist": request_data.get("reference_assist", {"enabled": False}),
        **({"reference_modules": request_data.get("reference_modules")} if isinstance(request_data.get("reference_modules"), dict) and any(isinstance(value, dict) and value.get("enabled") for value in (request_data.get("reference_modules") or {}).values()) else {}),
        **({"image_to_image": request_data.get("image_to_image")} if isinstance(request_data.get("image_to_image"), dict) and (request_data.get("image_to_image") or {}).get("enabled") else {}),
        **({"face_detailer": request_data.get("face_detailer")} if isinstance(request_data.get("face_detailer"), dict) and (request_data.get("face_detailer") or {}).get("enabled") else {}),
        **({"hand_detailer": request_data.get("hand_detailer")} if isinstance(request_data.get("hand_detailer"), dict) and (request_data.get("hand_detailer") or {}).get("enabled") else {}),
        **({"operation": request_data.get("operation")} if request_data.get("operation") else {}),
        **({"parent_history_id": request_data.get("parent_history_id")} if request_data.get("parent_history_id") else {}),
        **({"source_image": request_data.get("source_image")} if isinstance(request_data.get("source_image"), dict) else {}),
        "output_organization": organization_metadata(
            panel_id="anima",
            generation_method=output_method,
            original_prefix="Anima",
        ),
        "watermark": {"applied": False},
        "public_save": {"saved": False},
        "queue": {
            "status": "queued",
            "prompt_id": prompt_id,
            "submitted_at": now,
            "last_checked_at": None,
            "completed_at": None,
            "error": None,
        },
    }
    save_history_item(item)
    return normalize_history_item(item)


def complete_pending_history_item(history_id: str, result: Any) -> dict[str, Any] | None:
    if not getattr(result, "image_data_url", None):
        return None
    image_path, thumb_path = save_generated_image(result.image_data_url, history_id)
    store = _history_item_store(history_id)
    with _locked_history_item(history_id):
        if not store.path.exists():
            return None

        def complete(item: dict[str, Any]) -> dict[str, Any]:
            item = normalize_history_item(item)
            now = now_iso()
            item.update(
                {
                    "status": "completed",
                    "updated_at": now,
                    "image_path": str(image_path),
                    "thumbnail_path": str(thumb_path),
                    "filename": image_path.name,
                    "prompt_id": getattr(result, "prompt_id", item.get("prompt_id")),
                }
            )
            queue = item.get("queue") if isinstance(item.get("queue"), dict) else {}
            queue.update({"status": "completed", "completed_at": now, "last_checked_at": now, "error": None})
            item["queue"] = queue
            return item

        return normalize_history_item(store.update(complete, strict=True))


def update_pending_history_status(history_id: str, status: str, error: str | None = None) -> dict[str, Any] | None:
    store = _history_item_store(history_id)
    with _locked_history_item(history_id):
        if not store.path.exists():
            return None

        def update_status(item: dict[str, Any]) -> dict[str, Any]:
            item = normalize_history_item(item)
            now = now_iso()
            item["status"] = status
            item["updated_at"] = now
            queue = item.get("queue") if isinstance(item.get("queue"), dict) else {}
            queue.update({"status": status, "last_checked_at": now})
            if error is not None:
                queue["error"] = error
            item["queue"] = queue
            return item

        return normalize_history_item(store.update(update_status, strict=True))


def public_save_settings_hash(source: Path, apply_watermark: bool, watermark: dict[str, Any] | None) -> str:
    source_stat = source.stat()
    watermark_payload = {}
    if apply_watermark:
        watermark_payload = {
            "text": str((watermark or {}).get("text", "")),
            "position": str((watermark or {}).get("position", "bottom_right")),
            "opacity": float((watermark or {}).get("opacity", 0.72)),
            "size": int((watermark or {}).get("size", 36)),
            "margin": int((watermark or {}).get("margin", 28)),
        }
    payload = {
        "source_mtime_ns": source_stat.st_mtime_ns,
        "source_size_bytes": source_stat.st_size,
        "apply_watermark": apply_watermark,
        "watermark": watermark_payload,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def public_image_dimensions(path: Path) -> dict[str, int]:
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return {}
    return {"width": int(width), "height": int(height)}


def _public_save_output_path(history_id: str, source: Path, apply_watermark: bool) -> Path:
    suffix = "_wm" if apply_watermark else "_public"
    output = (PUBLIC_DIR / f"{history_id}{suffix}{source.suffix or '.png'}").resolve()
    public_root = PUBLIC_DIR.resolve()
    if not output.is_relative_to(public_root):
        raise ValueError("public save output path must stay under PUBLIC_DIR")
    return output


def public_save_cached_info(item: dict[str, Any], watermark: dict[str, Any] | None = None) -> dict[str, Any] | None:
    current = normalize_history_item(dict(item))
    history_id = str(current.get("id") or "")
    if not history_id:
        return None
    source = Path(str(current.get("image_path") or ""))
    if not source.exists():
        return None
    apply_watermark = bool(watermark and watermark.get("enabled", False))
    output = _public_save_output_path(history_id, source, apply_watermark)
    existing = current.get("public_save") if isinstance(current.get("public_save"), dict) else {}
    if not (
        output.exists()
        and bool(existing.get("saved"))
        and existing.get("settings_hash") == public_save_settings_hash(source, apply_watermark, watermark)
        and existing.get("path") == str(output)
    ):
        return None
    cached = dict(existing)
    cached["cached"] = True
    cached.setdefault("url", f"/api/history/{history_id}/public-image")
    cached.setdefault("filename", output.name)
    return cached


def _public_path_candidate(value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        return path
    candidate = (PUBLIC_DIR / path.name).resolve()
    public_root = PUBLIC_DIR.resolve()
    if not candidate.is_relative_to(public_root):
        return None
    return candidate


def resolve_public_image_path(item: dict[str, Any]) -> Path | None:
    current = normalize_history_item(dict(item))
    history_id = str(current.get("id") or "")
    if not history_id:
        return None
    public_save = current.get("public_save") if isinstance(current.get("public_save"), dict) else {}
    if not public_save.get("saved"):
        return None
    candidates: list[Path] = []
    for value in (public_save.get("path"), public_save.get("filename")):
        candidate = _public_path_candidate(value)
        if candidate:
            candidates.append(candidate)
    source = Path(str(current.get("image_path") or ""))
    suffix = source.suffix or ".png"
    watermark = current.get("watermark") if isinstance(current.get("watermark"), dict) else {}
    preferred_suffix = "_wm" if watermark.get("applied") else "_public"
    for marker in (preferred_suffix, "_wm", "_public"):
        candidates.append((PUBLIC_DIR / f"{history_id}{marker}{suffix}").resolve())
    public_root = PUBLIC_DIR.resolve()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_relative_to(public_root):
            continue
        if resolved.exists():
            return resolved
    return None


def copy_public_image(item: dict[str, Any], watermark: dict[str, Any] | None = None) -> dict[str, Any]:
    history_id = str(item.get("id") or "")
    store = _history_item_store(history_id)
    public_save: dict[str, Any] = {}

    def apply_public_save(current: dict[str, Any], *, normalize_current: bool = True) -> dict[str, Any]:
        nonlocal public_save
        if normalize_current:
            current = normalize_history_item(current)
        source = Path(current["image_path"])
        if not source.exists():
            raise FileNotFoundError("source image is missing")
        apply_watermark = bool(watermark and watermark.get("enabled", False))
        output = _public_save_output_path(history_id, source, apply_watermark)
        source_stat = source.stat()
        settings_hash = public_save_settings_hash(source, apply_watermark, watermark)
        existing = current.get("public_save") if isinstance(current.get("public_save"), dict) else {}
        cached = (
            output.exists()
            and bool(existing.get("saved"))
            and existing.get("settings_hash") == settings_hash
            and existing.get("path") == str(output)
        )
        if not cached:
            if apply_watermark:
                with Image.open(source).convert("RGBA") as image:
                    watermarked = apply_text_watermark(image, watermark or {})
                    watermarked.save(output)
            else:
                shutil.copy2(source, output)
        output_stat = output.stat()
        public_save = {
            "saved": True,
            "path": str(output),
            "url": f"/api/history/{history_id}/public-image",
            "filename": output.name,
            "created_at": existing.get("created_at") if cached else now_iso(),
            "updated_at": now_iso(),
            "cached": cached,
            "settings_hash": settings_hash,
            "source_mtime_ns": source_stat.st_mtime_ns,
            "source_size_bytes": source_stat.st_size,
            "size_bytes": output_stat.st_size,
            "watermark_text": (watermark or {}).get("text", ""),
            "watermark_position": (watermark or {}).get("position", "bottom_right"),
        }
        public_save.update(public_image_dimensions(output))
        current["public_save"] = public_save
        if apply_watermark:
            current["watermark"] = {
                "applied": True,
                "text": watermark.get("text", ""),
                "position": watermark.get("position", "bottom_right"),
                "opacity": watermark.get("opacity", 0.72),
                "size": watermark.get("size", 36),
            }
        else:
            current["watermark"] = {"applied": False}
        return current

    with _locked_history_item(history_id):
        if store.path.exists():
            current = store.update(apply_public_save, strict=True)
        else:
            current = apply_public_save(dict(item), normalize_current=False)
            store.write(_validate_history_item_json(current))
        item.update(current)
        return public_save


def apply_text_watermark(image: Image.Image, watermark: dict[str, Any]) -> Image.Image:
    text = str(watermark.get("text") or "@Luna_AIart_")
    opacity = max(0.0, min(float(watermark.get("opacity", 0.72)), 1.0))
    size = max(10, int(watermark.get("size", 36)))
    margin = max(0, int(watermark.get("margin", 28)))
    position = str(watermark.get("position", "bottom_right"))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/seguisb.ttf", size)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=max(1, size // 18))
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    positions = {
        "bottom_right": (image.width - text_w - margin, image.height - text_h - margin),
        "bottom_left": (margin, image.height - text_h - margin),
        "top_right": (image.width - text_w - margin, margin),
        "top_left": (margin, margin),
    }
    x, y = positions.get(position, positions["bottom_right"])
    alpha = int(255 * opacity)
    stroke = (0, 0, 0, min(220, alpha))
    fill = (255, 255, 255, alpha)
    draw.text((x, y), text, font=font, fill=fill, stroke_width=max(1, size // 18), stroke_fill=stroke)
    return Image.alpha_composite(image, overlay)
