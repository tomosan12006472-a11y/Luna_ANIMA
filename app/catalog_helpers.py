from __future__ import annotations

from typing import Any

from . import lora_catalog
from .favorites_store import localized_favorites


def original_character_lora_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    terms = {str(item.get("id") or "").lower(), str(item.get("display_name") or "").lower()}
    terms.update(str(term).lower() for term in item.get("trigger_words") or [])
    terms = {term for term in terms if term}
    candidates: list[dict[str, Any]] = []
    catalog_data = lora_catalog.catalog_with_favorites(lora_catalog.load_catalog())
    for lora in lora_catalog.selectable_loras(catalog_data):
        blob = " ".join(
            str(value or "")
            for value in [
                lora.get("lora_id"),
                lora.get("display_name"),
                lora.get("file_name"),
                lora.get("relative_path"),
                lora.get("notes"),
                " ".join(lora.get("trained_words") or []),
                " ".join(lora.get("tags") or []),
            ]
        ).lower()
        if any(term in blob for term in terms):
            candidates.append(lora)
    return candidates[:12]


def localized_favorite_item(favorite: dict[str, Any] | None) -> dict[str, Any] | None:
    if not favorite:
        return None
    key = "original_characters" if favorite.get("source") == "original_character" else "characters"
    payload = localized_favorites(
        {
            "characters": [favorite] if key == "characters" else [],
            "original_characters": [favorite] if key == "original_characters" else [],
        }
    )
    return payload[key][0] if payload[key] else None
