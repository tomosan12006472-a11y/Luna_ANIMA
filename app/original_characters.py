from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any

from .config import USER_DATA_DIR


ORIGINAL_CHARACTERS_PATH = USER_DATA_DIR / "original_characters.json"

DEFAULT_ORIGINAL_CHARACTERS: list[dict[str, Any]] = [
    {
        "id": "remy",
        "display_name": "Remy",
        "source": "original_character",
        "trigger_words": ["remy", "red eyes", "long white hair"],
        "positive_tags": ["remy", "red eyes", "long white hair"],
        "identity_prompt": "Remy is an original anime-style character with long white hair and red eyes.",
        "negative_guard": "different character, wrong hair color, wrong eye color, short hair, black hair, blue eyes",
        "default_lora": None,
        "favorite": True,
    }
]


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


def load_user_original_characters() -> list[dict[str, Any]]:
    if not ORIGINAL_CHARACTERS_PATH.exists():
        return []
    try:
        raw = json.loads(ORIGINAL_CHARACTERS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [normalize_original_character(item) for item in _items_from_raw(raw)]


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
    normalized = [normalize_original_character(item) for item in items]
    data = {"schema_version": 1, "updated_at": now_iso(), "items": normalized}
    ORIGINAL_CHARACTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ORIGINAL_CHARACTERS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def upsert_original_character(item: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_original_character(item)
    items = {entry["id"]: entry for entry in load_user_original_characters()}
    items[normalized["id"]] = normalized
    save_user_original_characters(list(items.values()))
    return normalized


def original_characters_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "schema_version": 1,
        "storage_path": str(ORIGINAL_CHARACTERS_PATH),
        "items": load_original_characters(include_defaults=True),
    }
