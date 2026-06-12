from __future__ import annotations

from datetime import datetime
import json
from threading import Lock
import time
from typing import Any

from ._shared_utils import write_json_atomic
from .config import ROOT_DIR


APP_SCOPE = "anima"
FLAGS_PATH = ROOT_DIR / "user_data" / "history_flags_anima.json"
VALID_FLAGS = {"favorite", "post_candidate", "hidden", "tags"}
_FLAGS_LOCK = Lock()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def default_flags() -> dict[str, Any]:
    return {"favorite": False, "post_candidate": False, "hidden": False, "tags": []}


def empty_payload() -> dict[str, Any]:
    return {"schema_version": 1, "app_scope": APP_SCOPE, "items": {}}


def load_history_flags() -> dict[str, Any]:
    with _FLAGS_LOCK:
        return _load_history_flags_unlocked()


def _load_history_flags_unlocked() -> dict[str, Any]:
    if not FLAGS_PATH.exists():
        return empty_payload()
    try:
        data = json.loads(FLAGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        time.sleep(0.05)
        try:
            data = json.loads(FLAGS_PATH.read_text(encoding="utf-8"))
        except Exception as second_error:
            raise RuntimeError("history flags are temporarily unreadable") from second_error
    if not isinstance(data, dict):
        return empty_payload()
    if data.get("app_scope") != APP_SCOPE:
        return empty_payload()
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    data.setdefault("schema_version", 1)
    data.setdefault("app_scope", APP_SCOPE)
    return data


def save_history_flags(data: dict[str, Any]) -> None:
    with _FLAGS_LOCK:
        _save_history_flags_unlocked(data)


def _save_history_flags_unlocked(data: dict[str, Any]) -> None:
    write_json_atomic(FLAGS_PATH, data)


def normalize_flags(value: Any) -> dict[str, Any]:
    flags = default_flags()
    if isinstance(value, dict):
        flags["favorite"] = bool(value.get("favorite"))
        flags["post_candidate"] = bool(value.get("post_candidate"))
        flags["hidden"] = bool(value.get("hidden"))
        tags = value.get("tags")
        flags["tags"] = [str(tag) for tag in tags] if isinstance(tags, list) else []
        if value.get("updated_at"):
            flags["updated_at"] = str(value.get("updated_at"))
    return flags


def item_key(item_or_id: dict[str, Any] | str) -> str:
    if isinstance(item_or_id, str):
        return item_or_id
    return str(item_or_id.get("id") or item_or_id.get("history_id") or item_or_id.get("image_path") or "")


def flags_for_item(item_or_id: dict[str, Any] | str) -> dict[str, Any]:
    key = item_key(item_or_id)
    data = load_history_flags()
    return normalize_flags(data.get("items", {}).get(key))


def attach_flags_to_item(item: dict[str, Any]) -> dict[str, Any]:
    item["flags"] = flags_for_item(item)
    return item


def attach_flags_to_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    data = load_history_flags()
    stored = data.get("items", {})
    for item in items:
        item["flags"] = normalize_flags(stored.get(item_key(item)))
    return items


def filter_items_by_flags(items: list[dict[str, Any]], filter_name: str = "all") -> list[dict[str, Any]]:
    normalized = (filter_name or "all").strip().lower()
    if normalized in {"favorite", "favorites"}:
        return [item for item in items if item.get("flags", {}).get("favorite")]
    if normalized in {"post_candidate", "post_candidates", "candidate", "candidates"}:
        return [item for item in items if item.get("flags", {}).get("post_candidate")]
    return items


def flag_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(items),
        "favorites": sum(1 for item in items if item.get("flags", {}).get("favorite")),
        "post_candidates": sum(1 for item in items if item.get("flags", {}).get("post_candidate")),
        "hidden": sum(1 for item in items if item.get("flags", {}).get("hidden")),
    }


def update_history_flags(history_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    clean_patch: dict[str, Any] = {}
    for key, value in (patch or {}).items():
        if key not in VALID_FLAGS:
            continue
        if key == "tags":
            clean_patch[key] = [str(tag) for tag in value] if isinstance(value, list) else []
        else:
            clean_patch[key] = bool(value)
    with _FLAGS_LOCK:
        data = _load_history_flags_unlocked()
        items = data.setdefault("items", {})
        current = normalize_flags(items.get(history_id))
        current.update(clean_patch)
        current["updated_at"] = now_iso()
        items[history_id] = current
        _save_history_flags_unlocked(data)
        return current
