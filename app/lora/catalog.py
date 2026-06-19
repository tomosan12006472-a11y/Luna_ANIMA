from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from threading import Lock
import time
from typing import Any

from .._shared_utils import clamp_strength, write_json_atomic
from .favorites import _favorite_match_keys, favorite_key_set, load_lora_favorites
from .paths import APP_SCOPE, CATALOG_PATH, slug
from .scan import scan_local_loras


_CATALOG_LOCK = Lock()

SLOT_DEFAULTS: dict[str, dict[str, Any]] = {
    "character": {"enabled": False, "lora_id": "none", "model_strength": 0.70, "clip_strength": 0.70, "max_strength": 1.0},
    "style": {"enabled": False, "lora_id": "none", "model_strength": 0.25, "clip_strength": 0.25, "max_strength": 1.0},
    "official_hires": {"enabled": False, "lora_id": "none", "model_strength": 0.60, "clip_strength": 0.60, "max_strength": 1.00},
    "turbo": {"enabled": False, "lora_id": "none", "model_strength": 0.60, "clip_strength": 0.60, "max_strength": 1.00},
}


def default_catalog() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "app_scope": APP_SCOPE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": scan_local_loras(),
    }


def load_catalog() -> dict[str, Any]:
    with _CATALOG_LOCK:
        return _load_catalog_unlocked()


def _load_catalog_unlocked() -> dict[str, Any]:
    if not CATALOG_PATH.exists():
        return default_catalog()
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        time.sleep(0.05)
        try:
            data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception as second_error:
            raise RuntimeError("lora catalog is temporarily unreadable") from second_error
    if not isinstance(data, dict):
        return default_catalog()
    items = data.get("items")
    if not isinstance(items, list):
        data["items"] = []
    else:
        for item in items:
            if isinstance(item, dict):
                item["max_strength"] = 1.0
    data.setdefault("schema_version", 1)
    data.setdefault("app_scope", APP_SCOPE)
    return data


def refresh_catalog() -> dict[str, Any]:
    catalog = default_catalog()
    with _CATALOG_LOCK:
        write_json_atomic(CATALOG_PATH, catalog)
    return catalog


def catalog_with_favorites(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    data = deepcopy(catalog or load_catalog())
    favorite_data = load_lora_favorites()
    keys = favorite_key_set(favorite_data)
    favorites = favorite_data.get("favorites") or {}
    favorite_count = 0
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        item_keys = _favorite_match_keys(item)
        favorite = bool(item_keys & keys)
        item["favorite"] = favorite
        if favorite:
            favorite_count += 1
            matched = next((favorites.get(key) for key in item_keys if isinstance(favorites.get(key), dict)), None)
            if matched:
                item["favorite_added_at"] = matched.get("added_at", "")
    data["favorite_count"] = favorite_count
    return data


def _is_selectable(item: dict[str, Any]) -> bool:
    return item.get("app_scope") == APP_SCOPE and item.get("status") == "available"


def selectable_loras(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = catalog_with_favorites(catalog)
    return [deepcopy(item) for item in data.get("items", []) if isinstance(item, dict) and _is_selectable(item)]


def _selectable_loras_without_favorites(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = deepcopy(catalog or load_catalog())
    return [deepcopy(item) for item in data.get("items", []) if isinstance(item, dict) and _is_selectable(item)]


def find_selectable_lora(query: dict[str, Any]) -> dict[str, Any] | None:
    query_keys = _favorite_match_keys(query)
    for item in selectable_loras():
        if _favorite_match_keys(item) & query_keys:
            return item
    return None


def _find_selectable_lora_without_favorites(query: dict[str, Any]) -> dict[str, Any] | None:
    query_keys = _favorite_match_keys(query)
    for item in _selectable_loras_without_favorites():
        if _favorite_match_keys(item) & query_keys:
            return item
    return None


def normalize_lora_slots(loras: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    catalog_items = {str(item.get("lora_id")): item for item in selectable_loras()}
    normalized: list[dict[str, Any]] = []
    for raw in loras or []:
        if not isinstance(raw, dict):
            continue
        enabled = bool(raw.get("enabled", True))
        mode = str(raw.get("mode") or "ALL")
        lora_id = str(raw.get("lora_id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not enabled or mode == "OFF" or lora_id == "none":
            continue
        source = "manual"
        display_name = name
        relative_path = name
        app_scope = APP_SCOPE
        category = str(raw.get("category") or "unknown")
        if lora_id and lora_id in catalog_items:
            item = catalog_items[lora_id]
            source = "catalog"
            display_name = str(item.get("display_name") or item.get("file_name") or lora_id)
            relative_path = str(item.get("relative_path") or item.get("file_name") or "")
            app_scope = str(item.get("app_scope") or APP_SCOPE)
            category = str(item.get("category") or category)
        elif not name:
            continue
        legacy_strength = clamp_strength(raw.get("weight", raw.get("strength", raw.get("model_strength", raw.get("model", 1.0)))), 1.0)
        model_strength = clamp_strength(raw.get("strength_model", raw.get("model_strength", raw.get("model_weight", raw.get("weight_model", raw.get("model", legacy_strength))))), legacy_strength)
        clip_strength = clamp_strength(raw.get("strength_clip", raw.get("clip_strength", raw.get("clip_weight", raw.get("weight_clip", raw.get("clip", legacy_strength))))), legacy_strength)
        normalized.append(
            {
                "slot": str(raw.get("slot") or "custom"),
                "enabled": True,
                "lora_id": lora_id or slug(relative_path),
                "display_name": display_name,
                "name": relative_path,
                "relative_path": relative_path,
                "model": model_strength,
                "clip": clip_strength,
                "model_strength": model_strength,
                "clip_strength": clip_strength,
                "strength_model": model_strength,
                "strength_clip": clip_strength,
                "weight": model_strength,
                "mode": mode,
                "app_scope": app_scope,
                "category": category,
                "source": source,
            }
        )
    return normalized
