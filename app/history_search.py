from __future__ import annotations

from datetime import datetime, time, timedelta
from pathlib import Path
import unicodedata
from typing import Any


TEXT_KEYS = {
    "positive",
    "negative",
    "common",
    "model",
    "sampler",
    "scheduler",
    "seed",
    "steps",
    "cfg",
    "shift",
    "model_sampling",
    "workflow_mode",
    "negative_mode",
    "negative_preset",
    "dynamic_prompt",
    "rating",
    "natural_description",
    "character_names",
    "characters",
    "original_character",
    "loras",
    "official_loras",
    "hires_fix",
    "reference_assist",
    "reference_modules",
    "image_to_image",
    "face_detailer",
    "operation",
    "parent_history_id",
    "prompt_id",
    "filename",
    "status",
    "source",
}


def normalize_search_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    return " ".join(text.replace("\n", " ").replace("\t", " ").casefold().split())


def query_tokens(q: str | None) -> list[str]:
    return [token for token in normalize_search_text(q).split(" ") if token]


def _iter_search_values(value: Any, *, depth: int = 0) -> list[str]:
    if value is None or depth > 4:
        return []
    if isinstance(value, (str, int, float, bool)):
        text = str(value)
        if len(text) > 2000:
            text = text[:2000]
        return [text]
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in {"image_data_url", "image", "thumbnail", "payload"}:
                continue
            parts.append(key_text)
            parts.extend(_iter_search_values(item, depth=depth + 1))
        return parts
    if isinstance(value, list):
        parts: list[str] = []
        for item in value[:80]:
            parts.extend(_iter_search_values(item, depth=depth + 1))
        return parts
    return [str(value)]


def build_search_document(item: dict[str, Any]) -> str:
    values: list[str] = []
    for key in TEXT_KEYS:
        values.extend(_iter_search_values(item.get(key)))
    for lora in item.get("loras") or []:
        values.extend(_iter_search_values(lora))
    values.extend(_iter_search_values(item.get("official_loras")))
    values.extend(_iter_search_values(item.get("flags")))
    return normalize_search_text(" ".join(str(value) for value in values if value is not None))


def parse_history_datetime(item: dict[str, Any]) -> datetime | None:
    for key in ("created_at", "generated_at", "timestamp", "updated_at"):
        value = item.get(key)
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value)).astimezone()
            except Exception:
                continue
        text = str(value or "").strip()
        if not text:
            continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(text, fmt)
                except ValueError:
                    pass
    for key in ("image_path", "thumbnail_path"):
        path_text = str(item.get(key) or "")
        if not path_text:
            continue
        try:
            path = Path(path_text)
            if path.exists():
                return datetime.fromtimestamp(path.stat().st_mtime).astimezone()
        except Exception:
            continue
    return None


def parse_date_start(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.combine(datetime.strptime(text, "%Y-%m-%d").date(), time.min)
    except ValueError:
        return None


def parse_date_end_exclusive(value: str | None) -> datetime | None:
    start = parse_date_start(value)
    return start + timedelta(days=1) if start else None


def normalize_hires_mode(value: Any) -> str:
    if isinstance(value, dict):
        if not value.get("enabled"):
            return "off"
        value = value.get("mode") or value.get("upscale_mode") or value.get("type")
    text = normalize_search_text(value)
    if text in {"", "none", "off", "false", "0"}:
        return "off"
    if "latent" in text:
        return "latent"
    if "model" in text or "upscale" in text:
        return "model"
    return text


def reference_state(item: dict[str, Any]) -> str:
    ref = item.get("reference_assist") or item.get("reference") or {}
    if isinstance(ref, dict):
        if ref.get("enabled") or ref.get("image_id") or ref.get("image_path") or ref.get("controlnet_model"):
            return "used"
    return "not_used"


def field_contains(item: dict[str, Any], keys: list[str], needle: str | None) -> bool:
    normalized = normalize_search_text(needle)
    if not normalized:
        return True
    for key in keys:
        if normalized in normalize_search_text(" ".join(_iter_search_values(item.get(key)))):
            return True
    return False


def item_matches(item: dict[str, Any], filters: dict[str, Any]) -> bool:
    doc = build_search_document(item)
    if any(token not in doc for token in query_tokens(filters.get("q"))):
        return False

    created = parse_history_datetime(item)
    start = parse_date_start(filters.get("date_from"))
    end = parse_date_end_exclusive(filters.get("date_to"))
    if start or end:
        if created is None:
            return False
        if start and created.replace(tzinfo=None) < start:
            return False
        if end and created.replace(tzinfo=None) >= end:
            return False

    if not field_contains(item, ["model"], filters.get("model")):
        return False
    if not field_contains(item, ["loras", "official_loras"], filters.get("lora")):
        return False
    seed = normalize_search_text(filters.get("seed"))
    if seed and normalize_search_text(item.get("seed")) != seed:
        return False
    hires_mode = normalize_search_text(filters.get("hires_mode"))
    if hires_mode and hires_mode != "any" and normalize_hires_mode(item.get("hires_fix")) != hires_mode:
        return False
    reference = normalize_search_text(filters.get("reference"))
    if reference and reference != "any" and reference_state(item) != reference:
        return False
    if not field_contains(item, ["sampler"], filters.get("sampler")):
        return False
    if not field_contains(item, ["scheduler"], filters.get("scheduler")):
        return False
    rating = normalize_search_text(filters.get("rating"))
    if rating and rating != "any" and normalize_search_text(item.get("rating")) != rating:
        return False
    if not field_contains(item, ["characters", "character_names", "original_character", "positive", "natural_description"], filters.get("character")):
        return False
    return True


def search_history_items(
    items: list[dict[str, Any]],
    *,
    limit: int = 20,
    offset: int = 0,
    **filters: Any,
) -> tuple[list[dict[str, Any]], int]:
    filtered = [item for item in items if item_matches(item, filters)]
    start = max(0, int(offset or 0))
    page_limit = max(1, min(int(limit or 20), 100))
    return filtered[start : start + page_limit], len(filtered)
