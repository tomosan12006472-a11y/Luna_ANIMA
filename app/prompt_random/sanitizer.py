from __future__ import annotations

import re
from typing import Any

from ..prompt_converter import SCORE_TAG_RE, normalize_tag_prompt, split_prompt_tags
from .settings import (
    CHARACTER_IDENTITY_RE,
    CHARACTER_MOTIF_OVERRIDE_RE,
    CHARACTER_MOTIF_RE,
    DISALLOWED_RANDOM_TAG_KEYS,
    DISALLOWED_RANDOM_TAG_RE,
    HAIR_EYE_COLOR_RE,
    HEAVY_RANDOM_MOTIF_RE,
    LIGHT_PROP_WEAPON_RE,
    MAX_POSITIVE_COMPLETION_TAG_CHARS,
    MAX_POSITIVE_COMPLETION_TAGS,
    MAX_RANDOM_TAG_CHARS,
    MAX_RANDOM_TAG_LIMITS_BY_STRENGTH,
    MAX_RANDOM_TAGS,
    MODE_POSITIVE_COMPLETION,
    MODE_RANDOM,
    SMALL_PROP_RE,
    STRENGTH_REFERENCE_568,
    SWIMWEAR_RE,
    _is_legacy_568_context,
)


def _fallback_prompt_random_tags(context: dict[str, Any]) -> str:
    from .fallback import fallback_prompt_random_tags

    return fallback_prompt_random_tags(context)


def _identity_terms(text: Any) -> set[str]:
    return {match.group(1).lower() for match in CHARACTER_IDENTITY_RE.finditer(str(text or ""))}


def _random_tag_key(tag: str) -> str:
    return re.sub(r"\s+", " ", str(tag or "").strip().lower()).strip(" ,;.")


def filter_disallowed_random_tags(tags: str) -> str:
    kept: list[str] = []
    for tag in split_prompt_tags(tags):
        key = _random_tag_key(tag)
        if not key:
            continue
        if SCORE_TAG_RE.fullmatch(key) or key in DISALLOWED_RANDOM_TAG_KEYS or DISALLOWED_RANDOM_TAG_RE.search(key):
            continue
        kept.append(tag)
    return ", ".join(kept)


def _character_reference_keys(context: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    references: list[Any] = []
    references.extend(context.get("characters") or [])
    references.extend(context.get("character_metadata") or [])
    for character in references:
        if isinstance(character, str):
            values = [character]
        elif isinstance(character, dict):
            values = [
                str(character.get(field) or "").strip()
                for field in ("prompt_tag", "prompt_safe_name", "display_name", "display_name_ja", "name", "id")
            ]
        else:
            values = []
        for value in values:
            if not value:
                continue
            normalized = _random_tag_key(value)
            if normalized:
                keys.add(normalized)
            for part in re.split(r"[()（）/\\|,]+|\s+from\s+", value, flags=re.IGNORECASE):
                part_key = _random_tag_key(part)
                if len(part_key) >= 3:
                    keys.add(part_key)
    return keys


def filter_character_reference_tags(tags: str, context: dict[str, Any]) -> str:
    reference_keys = _character_reference_keys(context)
    if not reference_keys:
        return tags
    kept: list[str] = []
    for tag in split_prompt_tags(tags):
        key = _random_tag_key(tag)
        if key in reference_keys:
            continue
        if any((len(ref) >= 3 and (key.startswith(ref) or ref.startswith(key))) for ref in reference_keys):
            continue
        kept.append(tag)
    return ", ".join(kept)


def _character_motif_override_requested(context: dict[str, Any]) -> bool:
    text = ", ".join(
        [
            str(context.get("existing_positive") or ""),
            str(context.get("prompt_random_collect_instruction") or ""),
        ]
    )
    return bool(CHARACTER_MOTIF_OVERRIDE_RE.search(text))


def filter_character_motif_tags(tags: str, context: dict[str, Any]) -> str:
    if context.get("prompt_random_collect_use_character_motifs", True) or _character_motif_override_requested(context):
        return tags
    kept: list[str] = []
    for tag in split_prompt_tags(tags):
        if CHARACTER_MOTIF_RE.search(tag):
            continue
        kept.append(tag)
    return ", ".join(kept)


def filter_heavy_random_motif_tags(tags: str, context: dict[str, Any]) -> str:
    if str(context.get("prompt_random_collect_mode") or MODE_RANDOM) != MODE_RANDOM:
        return tags
    if str(context.get("prompt_random_collect_strength") or "standard") == "rich":
        return tags
    if _character_motif_override_requested(context):
        return tags
    kept: list[str] = []
    for tag in split_prompt_tags(tags):
        if HEAVY_RANDOM_MOTIF_RE.search(tag) and not (SMALL_PROP_RE.search(tag) and LIGHT_PROP_WEAPON_RE.search(tag)):
            continue
        kept.append(tag)
    return ", ".join(kept)


def filter_outfit_replacement_tags(tags: str, context: dict[str, Any]) -> str:
    existing_positive = str(context.get("existing_positive") or "")
    if not SWIMWEAR_RE.search(existing_positive):
        return tags
    kept: list[str] = []
    for tag in split_prompt_tags(tags):
        if SWIMWEAR_RE.search(tag):
            continue
        kept.append(tag)
    return ", ".join(kept)


def filter_reference_568_identity_overrides(tags: str, context: dict[str, Any]) -> str:
    if str(context.get("prompt_random_collect_strength") or "standard") != STRENGTH_REFERENCE_568:
        return tags
    existing_positive = str(context.get("existing_positive") or "")
    kept: list[str] = []
    for tag in split_prompt_tags(tags):
        match = HAIR_EYE_COLOR_RE.search(tag)
        if match and match.group(0).lower() not in existing_positive.lower():
            continue
        kept.append(tag)
    return ", ".join(kept)


def clamp_prompt_random_tags(tags: str, *, max_tags: int = MAX_RANDOM_TAGS, max_chars: int = MAX_RANDOM_TAG_CHARS) -> str:
    kept: list[str] = []
    for tag in split_prompt_tags(tags):
        candidate = ", ".join([*kept, tag])
        if kept and len(candidate) > max_chars:
            break
        kept.append(tag)
        if len(kept) >= max_tags:
            break
    return ", ".join(kept).strip(" ,")


def prompt_random_limits(context: dict[str, Any]) -> tuple[int, int]:
    mode = str(context.get("prompt_random_collect_mode") or MODE_RANDOM)
    if mode == MODE_POSITIVE_COMPLETION:
        return MAX_POSITIVE_COMPLETION_TAGS, MAX_POSITIVE_COMPLETION_TAG_CHARS
    strength = str(context.get("prompt_random_collect_strength") or "standard")
    return MAX_RANDOM_TAG_LIMITS_BY_STRENGTH.get(strength, MAX_RANDOM_TAG_LIMITS_BY_STRENGTH["standard"])


def strip_character_identity_tags(tags: str, existing_positive: Any) -> str:
    allowed_terms = _identity_terms(existing_positive)
    kept: list[str] = []
    for tag in split_prompt_tags(tags):
        terms = _identity_terms(tag)
        if terms and not terms.issubset(allowed_terms):
            continue
        kept.append(tag)
    return ", ".join(kept)
def sanitize_generated_random_tags(raw_tags: Any, context: dict[str, Any]) -> str:
    existing_positive = context.get("existing_positive", "")
    max_tags, max_chars = prompt_random_limits(context)
    tags = normalize_tag_prompt(raw_tags, existing_positive)
    tags = filter_disallowed_random_tags(tags)
    if _is_legacy_568_context(context):
        if context.get("suppress_character_identity"):
            tags = strip_character_identity_tags(tags, existing_positive)
        tags = clamp_prompt_random_tags(tags, max_tags=max_tags, max_chars=max_chars)
        if tags:
            return tags

        tags = normalize_tag_prompt(_fallback_prompt_random_tags(context), existing_positive)
        tags = filter_disallowed_random_tags(tags)
        if context.get("suppress_character_identity"):
            tags = strip_character_identity_tags(tags, existing_positive)
        return clamp_prompt_random_tags(tags, max_tags=max_tags, max_chars=max_chars)

    tags = filter_character_reference_tags(tags, context)
    tags = filter_character_motif_tags(tags, context)
    tags = filter_heavy_random_motif_tags(tags, context)
    tags = filter_outfit_replacement_tags(tags, context)
    tags = filter_reference_568_identity_overrides(tags, context)
    if context.get("suppress_character_identity"):
        tags = strip_character_identity_tags(tags, existing_positive)
    tags = clamp_prompt_random_tags(tags, max_tags=max_tags, max_chars=max_chars)
    if tags:
        return tags

    tags = normalize_tag_prompt(_fallback_prompt_random_tags(context), existing_positive)
    tags = filter_disallowed_random_tags(tags)
    tags = filter_character_reference_tags(tags, context)
    tags = filter_character_motif_tags(tags, context)
    tags = filter_heavy_random_motif_tags(tags, context)
    tags = filter_outfit_replacement_tags(tags, context)
    tags = filter_reference_568_identity_overrides(tags, context)
    if context.get("suppress_character_identity"):
        tags = strip_character_identity_tags(tags, existing_positive)
    return clamp_prompt_random_tags(tags, max_tags=max_tags, max_chars=max_chars)
