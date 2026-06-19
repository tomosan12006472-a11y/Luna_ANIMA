from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import RLock
from typing import Any

from ..storage.json_store import JsonStore
from .paths import APP_SCOPE, FAVORITES_PATH


_LORA_FAVORITES_LOCK = RLock()


class _FavoriteUpdateAbort(Exception):
    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__(response.get("message") or response.get("status") or "favorite update aborted")
        self.response = response


def _favorite_identity(item: dict[str, Any]) -> str:
    for key in ("lora_id", "relative_path", "file_name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _favorite_match_keys(item: dict[str, Any]) -> set[str]:
    return {str(item.get(key) or "").strip() for key in ("lora_id", "relative_path", "file_name") if str(item.get(key) or "").strip()}


def empty_lora_favorites() -> dict[str, Any]:
    return {"schema_version": 1, "app_scope": APP_SCOPE, "favorites": {}}


def _normalize_lora_favorites_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("app_scope") != APP_SCOPE:
        return empty_lora_favorites()
    favorites = data.get("favorites")
    if not isinstance(favorites, dict):
        data["favorites"] = {}
    data.setdefault("schema_version", 1)
    data.setdefault("app_scope", APP_SCOPE)
    return data


def _lora_favorites_store() -> JsonStore:
    return JsonStore(
        FAVORITES_PATH,
        default_factory=empty_lora_favorites,
        label="lora favorites",
        lock=_LORA_FAVORITES_LOCK,
        validator=_normalize_lora_favorites_payload,
    )


def load_lora_favorites() -> dict[str, Any]:
    with _LORA_FAVORITES_LOCK:
        return _load_lora_favorites_unlocked()


def _load_lora_favorites_unlocked() -> dict[str, Any]:
    return _lora_favorites_store().read(strict=True)


def write_lora_favorites(data: dict[str, Any]) -> None:
    with _LORA_FAVORITES_LOCK:
        _write_lora_favorites_unlocked(data)


def _write_lora_favorites_unlocked(data: dict[str, Any]) -> None:
    data["schema_version"] = 1
    data["app_scope"] = APP_SCOPE
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if not isinstance(data.get("favorites"), dict):
        data["favorites"] = {}
    _lora_favorites_store().write(data)


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
    try:
        with _LORA_FAVORITES_LOCK:
            def mutate(data: dict[str, Any]) -> dict[str, Any]:
                nonlocal item_response, removed_response

                data["schema_version"] = 1
                data["app_scope"] = APP_SCOPE
                data["updated_at"] = datetime.now().isoformat(timespec="seconds")
                if not isinstance(data.get("favorites"), dict):
                    data["favorites"] = {}
                favorites = data.setdefault("favorites", {})
                query_keys = _favorite_match_keys(query)
                existing_keys = [
                    key
                    for key, item in favorites.items()
                    if key in query_keys or (isinstance(item, dict) and _favorite_match_keys(item) & query_keys)
                ]
                currently_favorite = bool(existing_keys)
                desired = (not currently_favorite) if favorite is None else bool(favorite)

                if not desired:
                    for key in existing_keys:
                        favorites.pop(key, None)
                    removed_response = bool(existing_keys)
                    return data

                item = _find_selectable_lora_without_favorites(query)
                if item is None:
                    raise _FavoriteUpdateAbort(
                        {"ok": False, "favorite": False, "status": "not_selectable", "message": "LoRA is not selectable for this app scope."}
                    )
                key = _favorite_identity(item)
                if not key:
                    raise _FavoriteUpdateAbort(
                        {"ok": False, "favorite": False, "status": "missing_identity", "message": "LoRA does not have a stable identity."}
                    )
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
                return data

            _lora_favorites_store().update(mutate, strict=True)
    except _FavoriteUpdateAbort as exc:
        return exc.response
    if removed_response is not None:
        return {"ok": True, "favorite": False, "removed": removed_response, **list_lora_favorites()}
    response = list_lora_favorites()
    response.update({"favorite": True, "item": item_response})
    return response
