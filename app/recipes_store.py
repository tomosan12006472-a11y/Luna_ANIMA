from __future__ import annotations

from datetime import datetime
import json
import secrets
from threading import Lock
import time
from typing import Any

from ._shared_utils import write_json_atomic
from .config import ROOT_DIR


APP_SCOPE = "anima"
RECIPES_PATH = ROOT_DIR / "user_data" / "recipes_anima.json"
_RECIPES_LOCK = Lock()
MAX_NAME_LENGTH = 60
MAX_SUMMARY_LENGTH = 120


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _empty_payload() -> dict[str, Any]:
    return {"version": 1, "app_scope": APP_SCOPE, "items": []}


def _backup_broken_file() -> None:
    if not RECIPES_PATH.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = RECIPES_PATH.with_name(f"{RECIPES_PATH.stem}.broken_{stamp}{RECIPES_PATH.suffix}")
    RECIPES_PATH.replace(backup_path)


def _make_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"recipe_{stamp}_{secrets.token_hex(3)}"


def _recipe_name(name: Any, summary: Any = "") -> str:
    text = str(name or "").strip() or str(summary or "").strip() or "Untitled Recipe"
    return text[:MAX_NAME_LENGTH]


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    created_at = str(item.get("created_at") or _now())
    updated_at = str(item.get("updated_at") or created_at)
    request = item.get("request") if isinstance(item.get("request"), dict) else {}
    return {
        "id": str(item.get("id") or _make_id()),
        "name": _recipe_name(item.get("name"), item.get("summary")),
        "request": dict(request),
        "summary": str(item.get("summary") or "").strip()[:MAX_SUMMARY_LENGTH],
        "created_at": created_at,
        "updated_at": updated_at,
        "use_count": max(0, int(item.get("use_count") or 0)),
        "last_used_at": item.get("last_used_at") or None,
    }


def _load_payload() -> dict[str, Any]:
    with _RECIPES_LOCK:
        return _load_payload_unlocked()


def _load_payload_unlocked() -> dict[str, Any]:
    if not RECIPES_PATH.exists():
        return _empty_payload()
    try:
        data = json.loads(RECIPES_PATH.read_text(encoding="utf-8"))
    except Exception:
        time.sleep(0.05)
        try:
            data = json.loads(RECIPES_PATH.read_text(encoding="utf-8"))
        except Exception:
            _backup_broken_file()
            return _empty_payload()
    if not isinstance(data, dict):
        return _empty_payload()
    items = data.get("items")
    if not isinstance(items, list):
        items = []
    normalized = [_normalize_item(item) for item in items if isinstance(item, dict)]
    return {"version": 1, "app_scope": APP_SCOPE, "items": normalized}


def _save_payload(payload: dict[str, Any]) -> dict[str, Any]:
    with _RECIPES_LOCK:
        return _save_payload_unlocked(payload)


def _save_payload_unlocked(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "version": 1,
        "app_scope": APP_SCOPE,
        "items": [_normalize_item(item) for item in payload.get("items", []) if isinstance(item, dict)],
    }
    write_json_atomic(RECIPES_PATH, normalized)
    return normalized


def list_recipes() -> dict[str, Any]:
    payload = _load_payload()
    payload["items"].sort(key=lambda item: (item.get("last_used_at") or item.get("created_at") or ""), reverse=True)
    return payload


def add_recipe(name: str, summary: str, request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("Recipe request must be an object")
    now = _now()
    item = _normalize_item({
        "id": _make_id(),
        "name": _recipe_name(name, summary),
        "summary": str(summary or "").strip()[:MAX_SUMMARY_LENGTH],
        "request": dict(request),
        "created_at": now,
        "updated_at": now,
        "use_count": 0,
        "last_used_at": None,
    })
    with _RECIPES_LOCK:
        payload = _load_payload_unlocked()
        payload["items"].insert(0, item)
        _save_payload_unlocked(payload)
        return item


def delete_recipe(recipe_id: str) -> bool:
    with _RECIPES_LOCK:
        payload = _load_payload_unlocked()
        before = len(payload["items"])
        payload["items"] = [item for item in payload["items"] if item.get("id") != recipe_id]
        removed = len(payload["items"]) != before
        if removed:
            _save_payload_unlocked(payload)
        return removed


def mark_recipe_used(recipe_id: str) -> dict[str, Any]:
    with _RECIPES_LOCK:
        payload = _load_payload_unlocked()
        for index, item in enumerate(payload["items"]):
            if item.get("id") != recipe_id:
                continue
            next_item = {
                **item,
                "use_count": int(item.get("use_count") or 0) + 1,
                "last_used_at": _now(),
                "updated_at": _now(),
            }
            payload["items"][index] = _normalize_item(next_item)
            _save_payload_unlocked(payload)
            return payload["items"][index]
    raise KeyError(recipe_id)
