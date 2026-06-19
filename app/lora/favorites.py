from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from threading import Lock
import time
from typing import Any

from .._shared_utils import write_json_atomic
from .paths import APP_SCOPE, FAVORITES_PATH


_LORA_FAVORITES_LOCK = Lock()


def _favorite_identity(item: dict[str, Any]) -> str:
    for key in ("lora_id", "relative_path", "file_name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _favorite_match_keys(item: dict[str, Any]) -> set[str]:
    return {str(item.get(key) or "").strip() for key in ("lora_id", "relative_path", "file_name") if str(item.get(key) or "").strip()}


def load_lora_favorites() -> dict[str, Any]:
    with _LORA_FAVORITES_LOCK:
        return _load_lora_favorites_unlocked()


def _load_lora_favorites_unlocked() -> dict[str, Any]:
    if not FAVORITES_PATH.exists():
        return {"schema_version": 1, "app_scope": APP_SCOPE, "favorites": {}}
    try:
        data = json.loads(FAVORITES_PATH.read_text(encoding="utf-8"))
    except Exception:
        time.sleep(0.05)
        try:
            data = json.loads(FAVORITES_PATH.read_text(encoding="utf-8"))
        except Exception as second_error:
            raise RuntimeError("lora favorites are temporarily unreadable") from second_error
    if not isinstance(data, dict) or data.get("app_scope") != APP_SCOPE:
        return {"schema_version": 1, "app_scope": APP_SCOPE, "favorites": {}}
    favorites = data.get("favorites")
    if not isinstance(favorites, dict):
        data["favorites"] = {}
    data.setdefault("schema_version", 1)
    data.setdefault("app_scope", APP_SCOPE)
    return data


def write_lora_favorites(data: dict[str, Any]) -> None:
    with _LORA_FAVORITES_LOCK:
        _write_lora_favorites_unlocked(data)


def _write_lora_favorites_unlocked(data: dict[str, Any]) -> None:
    data["schema_version"] = 1
    data["app_scope"] = APP_SCOPE
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json_atomic(FAVORITES_PATH, data)


def favorite_key_set(data: dict[str, Any] | None = None) -> set[str]:
    source = data or load_lora_favorites()
    keys: set[str] = set()
    for key, item in (source.get("favorites") or {}).items():
        if isinstance(key, str) and key:
            keys.add(key)
        if isinstance(item, dict):
            keys.update(_favorite_match_keys(item))
    return keys


def list_lora_favorites() -> dict[str, Any]:
    from .catalog import selectable_loras

    data = load_lora_favorites()
    selectable = selectable_loras()
    available_keys = set().union(*(_favorite_match_keys(item) for item in selectable)) if selectable else set()
    items: list[dict[str, Any]] = []
    for key, favorite in (data.get("favorites") or {}).items():
        if not isinstance(favorite, dict):
            continue
        record = deepcopy(favorite)
        record.setdefault("lora_id", key)
        record["available"] = bool(_favorite_match_keys(record) & available_keys)
        items.append(record)
    return {"ok": True, **data, "items": items, "favorite_count": len(items)}


def set_lora_favorite(query: dict[str, Any], favorite: bool | None = None) -> dict[str, Any]:
    from .catalog import _find_selectable_lora_without_favorites

    item_response: dict[str, Any] | None = None
    removed_response: bool | None = None
    with _LORA_FAVORITES_LOCK:
        data = _load_lora_favorites_unlocked()
        favorites = data.setdefault("favorites", {})
        query_keys = _favorite_match_keys(query)
        existing_keys = [key for key, item in favorites.items() if key in query_keys or (isinstance(item, dict) and _favorite_match_keys(item) & query_keys)]
        currently_favorite = bool(existing_keys)
        desired = (not currently_favorite) if favorite is None else bool(favorite)

        if not desired:
            for key in existing_keys:
                favorites.pop(key, None)
            _write_lora_favorites_unlocked(data)
            removed_response = bool(existing_keys)

        else:
            item = _find_selectable_lora_without_favorites(query)
            if item is None:
                return {"ok": False, "favorite": False, "status": "not_selectable", "message": "LoRA is not selectable for this app scope."}
            key = _favorite_identity(item)
            if not key:
                return {"ok": False, "favorite": False, "status": "missing_identity", "message": "LoRA does not have a stable identity."}
            now = datetime.now().isoformat(timespec="seconds")
            favorites[key] = {
                "lora_id": item.get("lora_id", ""),
                "relative_path": item.get("relative_path", ""),
                "file_name": item.get("file_name", ""),
                "display_name": item.get("display_name") or item.get("file_name") or item.get("lora_id") or key,
                "app_scope": APP_SCOPE,
                "added_at": (favorites.get(key, {}).get("added_at") if isinstance(favorites.get(key), dict) else "") or now,
            }
            item_response = dict(favorites[key])
            _write_lora_favorites_unlocked(data)
    if removed_response is not None:
        return {"ok": True, "favorite": False, "removed": removed_response, **list_lora_favorites()}
    response = list_lora_favorites()
    response.update({"favorite": True, "item": item_response})
    return response
