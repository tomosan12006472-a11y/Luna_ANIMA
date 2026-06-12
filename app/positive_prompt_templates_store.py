from __future__ import annotations

import json
from typing import Any

from .config import ROOT_DIR


TEMPLATES_PATH = ROOT_DIR / "config" / "positive_prompt_templates.json"
MAX_LIMIT = 100


def _load_payload() -> dict[str, Any]:
    if not TEMPLATES_PATH.exists():
        return {"version": 1, "source": "ComfyUI_MobilePanel", "items": [], "categories": []}
    try:
        data = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"version": 1, "source": "ComfyUI_MobilePanel", "items": [], "categories": [], "error": str(exc)}
    if not isinstance(data, dict):
        return {"version": 1, "source": "ComfyUI_MobilePanel", "items": [], "categories": []}
    items = [item for item in data.get("items", []) if isinstance(item, dict)]
    categories = sorted({str(item.get("category") or "other") for item in items})
    return {**data, "items": items, "categories": categories}


def _matches_query(item: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = "\n".join(
        str(part or "")
        for part in [
            item.get("title"),
            item.get("category"),
            item.get("positive_prompt"),
            item.get("note"),
            " ".join(str(tag or "") for tag in item.get("tags", []) if tag),
        ]
    ).casefold()
    return query.casefold() in haystack


def list_positive_prompt_templates(query: str = "", category: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    payload = _load_payload()
    items = payload.get("items", [])
    query = str(query or "").strip()
    category = str(category or "").strip()
    if category and category != "all":
        items = [item for item in items if str(item.get("category") or "") == category]
    if query:
        items = [item for item in items if _matches_query(item, query)]

    total = len(items)
    offset = max(0, int(offset or 0))
    limit = min(MAX_LIMIT, max(1, int(limit or 50)))
    page = items[offset : offset + limit]
    return {
        "ok": True,
        "version": payload.get("version", 1),
        "source": payload.get("source", "ComfyUI_MobilePanel"),
        "source_note": payload.get("source_note", ""),
        "count": total,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(page) < total,
        "categories": payload.get("categories", []),
        "items": page,
        "catalog_count": len(payload.get("items", [])),
        "excluded_count": int(payload.get("excluded_count") or 0),
        "source_mismatch_count": int(payload.get("source_mismatch_count") or 0),
    }
