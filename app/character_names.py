from __future__ import annotations

from functools import lru_cache
import json
import re
from typing import Any

from .config import ROOT_DIR


DISPLAY_NAMES_JA_PATH = ROOT_DIR / "config" / "character_display_names_ja.json"
CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
PAREN_RE = re.compile(r"\(([^()]*)\)")


def contains_cjk(text: Any) -> bool:
    return bool(CJK_RE.search(str(text or "")))


def normalize_prompt_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


@lru_cache(maxsize=1)
def load_display_names_ja() -> dict[str, str]:
    if not DISPLAY_NAMES_JA_PATH.exists():
        return {}
    try:
        raw = json.loads(DISPLAY_NAMES_JA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    names: dict[str, str] = {}
    for key, value in raw.items():
        prompt_key = normalize_prompt_key(key)
        display = str(value or "").strip()
        if prompt_key and display:
            names[prompt_key] = display
    return names


def display_name_ja(display_name: Any, prompt_tag: Any) -> str:
    prompt_key = normalize_prompt_key(prompt_tag)
    mapped = load_display_names_ja().get(prompt_key)
    if mapped:
        return mapped
    return str(display_name or "").strip()


def _title_word(word: str) -> str:
    raw = word.strip()
    if not raw:
        return ""
    lower = raw.lower()
    if lower in {"fgo", "2b", "3d"}:
        return lower.upper()
    if lower in {"tv", "ova"}:
        return lower.upper()
    if any(ch.isdigit() for ch in raw) and len(raw) <= 4:
        return raw.upper()
    return raw[:1].upper() + raw[1:]


def _humanize_english_tag(text: str) -> str:
    cleaned = re.sub(r"[_\s]+", " ", text.replace("\\", " ")).strip()
    if not cleaned:
        return ""
    return " ".join(_title_word(word) for word in cleaned.split())


def prompt_safe_character_name(display_name: Any, prompt_tag: Any) -> str:
    tag = str(prompt_tag or "").split(",", 1)[0].strip()
    if not tag:
        fallback = str(display_name or "").strip()
        return "" if contains_cjk(fallback) else fallback
    tag = tag.replace("\\(", "(").replace("\\)", ")")
    groups = [_humanize_english_tag(group) for group in PAREN_RE.findall(tag)]
    groups = [group for group in groups if group]
    base = PAREN_RE.sub("", tag).strip()
    base_label = _humanize_english_tag(base)
    if not base_label:
        return ""
    if len(groups) >= 2:
        descriptor = ", ".join(groups[:-1])
        return f"{base_label} ({descriptor}) from {groups[-1]}"
    if len(groups) == 1:
        return f"{base_label} from {groups[0]}"
    return base_label


def enrich_character_dict(item: dict[str, Any]) -> dict[str, Any]:
    data = dict(item)
    original = str(data.get("display_name") or data.get("name") or data.get("id") or "").strip()
    prompt_tag = str(data.get("prompt_tag") or "").strip()
    data.setdefault("display_name_original", original)
    data["display_name_ja"] = display_name_ja(original, prompt_tag)
    data["prompt_safe_name"] = prompt_safe_character_name(original, prompt_tag)
    return data


def character_entry_payload(entry: Any) -> dict[str, Any]:
    return enrich_character_dict(dict(getattr(entry, "__dict__", {}) or {}))


def localized_search_text(entry: Any) -> str:
    display = str(getattr(entry, "display_name", "") or "")
    prompt_tag = str(getattr(entry, "prompt_tag", "") or "")
    return " ".join(
        part
        for part in [
            str(getattr(entry, "search_text", "") or ""),
            display_name_ja(display, prompt_tag),
            prompt_safe_character_name(display, prompt_tag),
        ]
        if part
    ).lower()


def localize_favorites_payload(data: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "characters": [enrich_character_dict(item) for item in data.get("characters", [])],
        "original_characters": [enrich_character_dict(item) for item in data.get("original_characters", [])],
    }
