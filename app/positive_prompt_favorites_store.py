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
FAVORITES_PATH = ROOT_DIR / "user_data" / "positive_prompt_favorites_anima.json"
_FAVORITES_LOCK = Lock()
MAX_PROMPT_LENGTH = 12000
MAX_TITLE_LENGTH = 120
MAX_NOTE_LENGTH = 1000
MAX_TAGS = 20


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _empty_payload() -> dict[str, Any]:
    return {"version": 1, "app_scope": APP_SCOPE, "items": []}


def _backup_broken_file() -> None:
    if not FAVORITES_PATH.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = FAVORITES_PATH.with_name(f"{FAVORITES_PATH.stem}.broken_{stamp}{FAVORITES_PATH.suffix}")
    FAVORITES_PATH.replace(backup_path)


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.replace(";", ",").split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        tag = str(item or "").strip()
        key = tag.casefold()
        if not tag or key in seen:
            continue
        seen.add(key)
        tags.append(tag[:64])
        if len(tags) >= MAX_TAGS:
            break
    return tags


def _title_from_prompt(prompt: str) -> str:
    base = " ".join(prompt.replace("\n", " ").split())
    if base:
        return base[:40]
    return f"Positive Prompt {datetime.now().strftime('%Y-%m-%d %H:%M')}"


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    prompt = str(item.get("prompt") or "").strip()[:MAX_PROMPT_LENGTH]
    created_at = str(item.get("created_at") or _now())
    updated_at = str(item.get("updated_at") or created_at)
    title = str(item.get("title") or "").strip()[:MAX_TITLE_LENGTH] or _title_from_prompt(prompt)
    return {
        "id": str(item.get("id") or _make_id()),
        "title": title,
        "prompt": prompt,
        "source": str(item.get("source") or "positive_prompt"),
        "profile": str(item.get("profile") or APP_SCOPE),
        "tags": _normalize_tags(item.get("tags")),
        "favorite": bool(item.get("favorite", True)),
        "use_count": max(0, int(item.get("use_count") or 0)),
        "created_at": created_at,
        "updated_at": updated_at,
        "last_used_at": item.get("last_used_at") or None,
        "note": str(item.get("note") or "").strip()[:MAX_NOTE_LENGTH],
    }


def _make_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"ppfav_{stamp}_{secrets.token_hex(3)}"


def _load_payload() -> dict[str, Any]:
    with _FAVORITES_LOCK:
        return _load_payload_unlocked()


def _load_payload_unlocked() -> dict[str, Any]:
    if not FAVORITES_PATH.exists():
        return _empty_payload()
    try:
        data = json.loads(FAVORITES_PATH.read_text(encoding="utf-8"))
    except Exception:
        time.sleep(0.05)
        try:
            data = json.loads(FAVORITES_PATH.read_text(encoding="utf-8"))
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
    with _FAVORITES_LOCK:
        return _save_payload_unlocked(payload)


def _save_payload_unlocked(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "version": 1,
        "app_scope": APP_SCOPE,
        "items": [_normalize_item(item) for item in payload.get("items", []) if isinstance(item, dict)],
    }
    write_json_atomic(FAVORITES_PATH, normalized)
    return normalized


def list_positive_prompt_favorites() -> dict[str, Any]:
    payload = _load_payload()
    payload["items"].sort(key=lambda item: (item.get("last_used_at") or item.get("created_at") or ""), reverse=True)
    return payload


def add_positive_prompt_favorite(data: dict[str, Any]) -> dict[str, Any]:
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("Positive prompt is empty")
    now = _now()
    item = _normalize_item({
        **data,
        "id": _make_id(),
        "prompt": prompt,
        "created_at": now,
        "updated_at": now,
        "last_used_at": None,
        "use_count": 0,
        "profile": APP_SCOPE,
        "source": "positive_prompt",
        "favorite": True,
    })
    with _FAVORITES_LOCK:
        payload = _load_payload_unlocked()
        payload["items"].insert(0, item)
        _save_payload_unlocked(payload)
        return item


def update_positive_prompt_favorite(favorite_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    with _FAVORITES_LOCK:
        payload = _load_payload_unlocked()
        for index, item in enumerate(payload["items"]):
            if item.get("id") != favorite_id:
                continue
            next_item = {**item}
            for key in ("title", "prompt", "tags", "note", "favorite"):
                if key in patch and patch[key] is not None:
                    next_item[key] = patch[key]
            if not str(next_item.get("prompt") or "").strip():
                raise ValueError("Positive prompt is empty")
            next_item["updated_at"] = _now()
            payload["items"][index] = _normalize_item(next_item)
            _save_payload_unlocked(payload)
            return payload["items"][index]
    raise KeyError(favorite_id)


def delete_positive_prompt_favorite(favorite_id: str) -> bool:
    with _FAVORITES_LOCK:
        payload = _load_payload_unlocked()
        before = len(payload["items"])
        payload["items"] = [item for item in payload["items"] if item.get("id") != favorite_id]
        removed = len(payload["items"]) != before
        if removed:
            _save_payload_unlocked(payload)
        return removed


def mark_positive_prompt_favorite_used(favorite_id: str) -> dict[str, Any]:
    with _FAVORITES_LOCK:
        payload = _load_payload_unlocked()
        for index, item in enumerate(payload["items"]):
            if item.get("id") != favorite_id:
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
    raise KeyError(favorite_id)
