from __future__ import annotations

import re
from typing import Any

from ..prompt_converter import split_prompt_tags
from .sanitizer import _random_tag_key, sanitize_generated_random_tags
from .settings import _is_legacy_568_context


def _raw_item_tags(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("tags") or item.get("tags_en") or item.get("prompt") or item.get("text") or "").strip()
    return str(item or "").strip()


def normalize_prompt_random_collect_items(data: dict[str, Any], contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        raise ValueError("random collect response must include an items array")
    if len(raw_items) < len(contexts):
        raise ValueError(f"random collect returned {len(raw_items)} items for {len(contexts)} queued images")

    by_index: dict[int, Any] = {}
    ordered: list[Any] = []
    for position, raw in enumerate(raw_items):
        raw_index = raw.get("index") if isinstance(raw, dict) else None
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            index = position
        by_index[index] = raw
        ordered.append(raw)

    generated: list[dict[str, Any]] = []
    seen_tags: set[str] = set()
    seen_tag_keys: set[str] = set()
    legacy_568_contexts = bool(contexts) and all(_is_legacy_568_context(context) for context in contexts)
    for position, context in enumerate(contexts):
        index = int(context.get("index") or position)
        raw = by_index.get(index, ordered[position] if position < len(ordered) else {})
        tags = sanitize_generated_random_tags(_raw_item_tags(raw), context)
        if not legacy_568_contexts:
            unique_tags: list[str] = []
            for tag in split_prompt_tags(tags):
                tag_key = _random_tag_key(tag)
                if tag_key and tag_key in seen_tag_keys:
                    continue
                unique_tags.append(tag)
                if tag_key:
                    seen_tag_keys.add(tag_key)
            tags = ", ".join(unique_tags).strip(" ,") or sanitize_generated_random_tags("", context)
        tags = re.sub(r"\s+", " ", tags).strip(" ,")
        if not tags:
            raise ValueError(f"random collect item {index} did not include usable tags")
        key = tags.lower()
        if len(contexts) > 1 and key in seen_tags:
            raise ValueError("random collect returned duplicate tag sets")
        seen_tags.add(key)
        generated.append({"index": index, "seed": context.get("seed"), "tags": tags})
    return generated
