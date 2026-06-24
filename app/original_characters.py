from __future__ import annotations

from datetime import datetime
import re
from threading import RLock
from typing import Any

from .config import USER_DATA_DIR
from .storage.json_store import JsonStore


ORIGINAL_CHARACTERS_PATH = USER_DATA_DIR / "original_characters.json"

DEFAULT_ORIGINAL_CHARACTERS: list[dict[str, Any]] = []
_ORIGINAL_CHARACTERS_LOCK = RLock()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slug(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z]+", "_", value.strip().lower()).strip("_")
    return text or "original_character"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r",|\n", value) if item.strip()]
    return []


def normalize_original_character(item: dict[str, Any]) -> dict[str, Any]:
    display_name = str(item.get("display_name") or item.get("name") or item.get("id") or "").strip()
    character_id = str(item.get("id") or slug(display_name)).strip()
    trigger_words = _string_list(item.get("trigger_words"))
    positive_tags = _string_list(item.get("positive_tags") or item.get("prompt_tag"))
    if not positive_tags:
        positive_tags = trigger_words
    if not trigger_words:
        trigger_words = positive_tags
    prompt_tag = ", ".join(positive_tags)
    return {
        "id": character_id,
        "display_name": display_name or character_id,
        "source": "original_character",
        "kind": "original",
        "prompt_tag": prompt_tag,
        "trigger_words": trigger_words,
        "positive_tags": positive_tags,
        "identity_prompt": str(item.get("identity_prompt") or "").strip(),
        "negative_guard": str(item.get("negative_guard") or "").strip(),
        "default_lora": item.get("default_lora") or None,
        "favorite": bool(item.get("favorite", False)),
    }


def _items_from_raw(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        items = raw.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _empty_payload() -> dict[str, Any]:
    return {"schema_version": 1, "items": []}


def _normalize_payload(raw: Any) -> dict[str, Any]:
    data = _empty_payload()
    if isinstance(raw, dict) and raw.get("updated_at"):
        data["updated_at"] = str(raw.get("updated_at"))
    data["items"] = [normalize_original_character(item) for item in _items_from_raw(raw)]
    return data


def _original_characters_store() -> JsonStore:
    return JsonStore(
        ORIGINAL_CHARACTERS_PATH,
        default_factory=_empty_payload,
        label="original characters",
        lock=_ORIGINAL_CHARACTERS_LOCK,
        validator=_normalize_payload,
    )


def _load_payload_unlocked(*, strict: bool = False) -> dict[str, Any]:
    return _original_characters_store().read(strict=strict)


def _save_payload_unlocked(items: list[dict[str, Any]]) -> dict[str, Any]:
    data = {
        "schema_version": 1,
        "updated_at": now_iso(),
        "items": [normalize_original_character(item) for item in items],
    }
    _original_characters_store().write(data)
    return data


def load_user_original_characters(*, strict: bool = False) -> list[dict[str, Any]]:
    with _ORIGINAL_CHARACTERS_LOCK:
        payload = _load_payload_unlocked(strict=strict)
        return [dict(item) for item in payload.get("items", []) if isinstance(item, dict)]


def load_original_characters(include_defaults: bool = True) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    if include_defaults:
        for item in DEFAULT_ORIGINAL_CHARACTERS:
            normalized = normalize_original_character(item)
            merged[normalized["id"]] = normalized
    for item in load_user_original_characters():
        merged[item["id"]] = item
    return list(merged.values())


def save_user_original_characters(items: list[dict[str, Any]]) -> dict[str, Any]:
    with _ORIGINAL_CHARACTERS_LOCK:
        return _save_payload_unlocked(items)


def upsert_original_character(item: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_original_character(item)
    with _ORIGINAL_CHARACTERS_LOCK:
        payload = _load_payload_unlocked(strict=True)
        items = {entry["id"]: entry for entry in payload.get("items", []) if isinstance(entry, dict)}
        items[normalized["id"]] = normalized
        _save_payload_unlocked(list(items.values()))
    return normalized


def original_characters_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "schema_version": 1,
        "storage_path": str(ORIGINAL_CHARACTERS_PATH),
        "items": load_original_characters(include_defaults=True),
    }
