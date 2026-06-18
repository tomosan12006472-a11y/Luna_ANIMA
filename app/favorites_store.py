from __future__ import annotations

from datetime import datetime
import re
from threading import Lock
from typing import Any

from ._shared_utils import read_json_with_retry, write_json_atomic
from .character_names import localize_favorites_payload
from .config import FAVORITES_PATH
from .anima_adapter import catalog


FAVORITE_SOURCES = {"wai_characters", "original_character"}
_FAVORITES_LOCK = Lock()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def empty_favorites() -> dict[str, list[dict[str, Any]]]:
    return {"characters": [], "original_characters": []}


def slug(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー]+", "_", value.strip().lower()).strip("_")
    return text or "favorite"


def current_favorite_display_name(source: str, item: dict[str, Any], fallback_id: str) -> str:
    prompt_tag = str(item.get("prompt_tag") or "").strip()
    if source == "original_character":
        value = str(item.get("id") or item.get("display_name") or item.get("name") or "").strip()
        entry = catalog.original_by_id.get(value) or catalog.original_by_display.get(value)
        if not entry and prompt_tag:
            entry = next((candidate for candidate in catalog.original if candidate.prompt_tag == prompt_tag), None)
        if entry:
            return entry.display_name
    elif prompt_tag:
        entry = catalog.by_prompt.get(prompt_tag)
        if entry:
            return entry.display_name
    return str(item.get("display_name") or item.get("name") or fallback_id)


def normalize_favorites(raw: Any) -> dict[str, list[dict[str, Any]]]:
    data = empty_favorites()
    if not isinstance(raw, dict):
        return data
    seen: set[tuple[str, str]] = set()
    for key in ("characters", "original_characters"):
        values = raw.get(key, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or ("original_character" if key == "original_characters" else "wai_characters"))
            favorite_id = str(item.get("id") or make_favorite_id(source, item))
            dedupe = (source, favorite_id)
            if source not in FAVORITE_SOURCES or dedupe in seen:
                continue
            seen.add(dedupe)
            display_name = current_favorite_display_name(source, item, favorite_id)
            data[key].append(
                {
                    "source": source,
                    "id": favorite_id,
                    "name": display_name,
                    "display_name": display_name,
                    "prompt_tag": str(item.get("prompt_tag") or ""),
                    "category": str(item.get("category") or ""),
                    "note": str(item.get("note") or ""),
                    "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                    "sort_order": item.get("sort_order"),
                    "use_count": int(item.get("use_count") or 0),
                    "last_used_at": item.get("last_used_at"),
                    "created_at": str(item.get("created_at") or now_iso()),
                    "updated_at": str(item.get("updated_at") or item.get("created_at") or now_iso()),
                }
            )
    return data


def load_favorites() -> dict[str, list[dict[str, Any]]]:
    with _FAVORITES_LOCK:
        return _load_favorites_unlocked()


def _load_favorites_unlocked() -> dict[str, list[dict[str, Any]]]:
    if not FAVORITES_PATH.exists():
        return empty_favorites()
    raw = read_json_with_retry(FAVORITES_PATH, label="character favorites")
    return normalize_favorites(raw)


def save_favorites(data: dict[str, list[dict[str, Any]]]) -> None:
    with _FAVORITES_LOCK:
        _save_favorites_unlocked(data)


def _save_favorites_unlocked(data: dict[str, list[dict[str, Any]]]) -> None:
    write_json_atomic(FAVORITES_PATH, normalize_favorites(data))


def make_favorite_id(source: str, item: dict[str, Any]) -> str:
    display = str(item.get("display_name") or item.get("name") or "")
    prompt = str(item.get("prompt_tag") or "")
    return slug(f"{source}_{display}_{prompt}")


def find_catalog_entry(source: str, item: dict[str, Any]) -> dict[str, Any]:
    value = str(item.get("display_name") or item.get("name") or item.get("id") or "").strip()
    prompt_tag = str(item.get("prompt_tag") or "").strip()
    if source == "original_character":
        entry = catalog.original_by_id.get(value) or catalog.original_by_display.get(value)
        if not entry and prompt_tag:
            entry = next((candidate for candidate in catalog.original if candidate.prompt_tag == prompt_tag), None)
    else:
        entry = catalog.by_display.get(value) or catalog.by_prompt.get(value)
        if not entry and prompt_tag:
            entry = catalog.by_prompt.get(prompt_tag)
    if not entry:
        raise ValueError("Unknown favorite character")
    return {"id": entry.id, "display_name": entry.display_name, "prompt_tag": entry.prompt_tag, "kind": entry.kind}


def add_favorite(item: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, list[dict[str, Any]]]]:
    source = str(item.get("source") or "").strip()
    if source not in FAVORITE_SOURCES:
        raise ValueError("Unknown favorite source")
    catalog_entry = find_catalog_entry(source, item)
    now = now_iso()
    favorite = {
        "source": source,
        "id": catalog_entry.get("id") if source == "original_character" and catalog_entry.get("id") else make_favorite_id(source, catalog_entry),
        "name": catalog_entry["display_name"],
        "display_name": catalog_entry["display_name"],
        "prompt_tag": catalog_entry["prompt_tag"],
        "category": catalog_entry["kind"],
        "note": str(item.get("note") or ""),
        "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
        "sort_order": item.get("sort_order"),
        "use_count": 0,
        "last_used_at": None,
        "created_at": now,
        "updated_at": now,
    }
    with _FAVORITES_LOCK:
        data = _load_favorites_unlocked()
        key = "original_characters" if source == "original_character" else "characters"
        existing = next((entry for entry in data[key] if entry["id"] == favorite["id"]), None)
        if existing:
            return "already_exists", existing, data
        data[key].append(favorite)
        _save_favorites_unlocked(data)
        return "created", favorite, data


def remove_favorite(source: str, favorite_id: str) -> tuple[bool, dict[str, list[dict[str, Any]]]]:
    if source not in FAVORITE_SOURCES:
        raise ValueError("Unknown favorite source")
    with _FAVORITES_LOCK:
        data = _load_favorites_unlocked()
        key = "original_characters" if source == "original_character" else "characters"
        before = len(data[key])
        data[key] = [item for item in data[key] if item.get("id") != favorite_id]
        removed = len(data[key]) != before
        if removed:
            _save_favorites_unlocked(data)
        return removed, data


def mark_favorite_used(source: str, favorite_id: str) -> dict[str, Any] | None:
    if source not in FAVORITE_SOURCES:
        return None
    with _FAVORITES_LOCK:
        data = _load_favorites_unlocked()
        key = "original_characters" if source == "original_character" else "characters"
        for item in data[key]:
            if item.get("id") == favorite_id:
                item["use_count"] = int(item.get("use_count") or 0) + 1
                item["last_used_at"] = now_iso()
                item["updated_at"] = item["last_used_at"]
                _save_favorites_unlocked(data)
                return item
        return None


def localized_favorites(data: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return localize_favorites_payload(data)
