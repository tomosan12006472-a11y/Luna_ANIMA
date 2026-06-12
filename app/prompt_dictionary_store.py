from __future__ import annotations

import csv
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_RESULTS = 50
SHARED_DATA_DIR = Path(r"D:\AI\PromptDictionaryData\sd-webui-prompt-dictionary\data")
MAIN_TSV = "prompt_dictionary.tsv"
EXTRA_TSV = "danbooru_extra.tsv"


@dataclass
class _DictionaryCache:
    loaded_at: float = 0.0
    data_dir: Path | None = None
    entries: list[dict[str, Any]] | None = None
    warning: str | None = None


_CACHE = _DictionaryCache()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _candidate_data_dirs() -> list[Path]:
    dirs: list[Path] = []
    env_dir = os.environ.get("PROMPT_DICTIONARY_DATA_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir))
    dirs.extend(
        [
            SHARED_DATA_DIR,
            _repo_root() / "user_data" / "prompt_dictionary" / "data",
            _repo_root() / "user_data" / "prompt_dictionary",
        ]
    )
    return dirs


def _resolve_data_dir() -> Path | None:
    for data_dir in _candidate_data_dirs():
        if (data_dir / MAIN_TSV).exists():
            return data_dir
    return None


def _normalize(text: Any) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).lower()
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _split_values(text: Any) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    values = [part.strip() for part in re.split(r"[,;\n\t|/]+", raw) if part.strip()]
    return values[:24]


def _to_int(value: Any) -> int:
    try:
        return int(float(str(value or "0").replace(",", "")))
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", ""))
    except Exception:
        return 0.0


def _entry_from_row(row: dict[str, str], source: str) -> dict[str, Any] | None:
    tag = str(row.get("tag") or "").strip()
    if not tag:
        return None
    aliases = _split_values(row.get("aliases"))
    search_aliases = _split_values(row.get("search_aliases"))
    related_tags = _split_values(row.get("related_tags"))
    searchable_parts = [
        tag,
        tag.replace("_", " "),
        row.get("display_tag", ""),
        row.get("ja", ""),
        row.get("description", ""),
        row.get("dictionary_section", ""),
        " ".join(aliases),
        " ".join(search_aliases),
        " ".join(related_tags),
    ]
    return {
        "tag": tag,
        "insert_text": tag.replace("_", " "),
        "display_tag": row.get("display_tag") or tag,
        "ja": row.get("ja") or "",
        "description": row.get("description") or "",
        "aliases": aliases,
        "search_aliases": search_aliases,
        "related_tags": related_tags,
        "dictionary_section": row.get("dictionary_section") or "",
        "post_count": _to_int(row.get("post_count")),
        "rank_count": _to_int(row.get("rank_count")),
        "category": row.get("category") or "",
        "is_deprecated": str(row.get("is_deprecated") or "").lower() in {"1", "true", "yes"},
        "has_tag": str(row.get("has_tag") or "").lower() in {"1", "true", "yes"},
        "has_wiki": str(row.get("has_wiki") or "").lower() in {"1", "true", "yes"},
        "wiki_note": row.get("wiki_note") or "",
        "is_dictionary": str(row.get("is_dictionary") or "").lower() in {"1", "true", "yes"},
        "importance": _to_float(row.get("importance")),
        "source": source,
        "_search": _normalize(" ".join(searchable_parts)),
    }


def _read_tsv(path: Path, source: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        for row in reader:
            item = _entry_from_row(row, source)
            if item:
                items.append(item)
    return items


def _load_entries(force: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if _CACHE.entries is not None and not force:
        return _CACHE.entries, _status_from_cache()

    data_dir = _resolve_data_dir()
    if not data_dir:
        _CACHE.loaded_at = time.time()
        _CACHE.data_dir = None
        _CACHE.entries = []
        _CACHE.warning = "prompt dictionary data was not found"
        return _CACHE.entries, _status_from_cache()

    entries = _read_tsv(data_dir / MAIN_TSV, "prompt_dictionary")
    extra_path = data_dir / EXTRA_TSV
    if extra_path.exists():
        existing = {str(item["tag"]).lower(): item for item in entries}
        for item in _read_tsv(extra_path, "danbooru_extra"):
            key = str(item["tag"]).lower()
            if key in existing:
                current = existing[key]
                for field in ("ja", "description", "dictionary_section"):
                    if not current.get(field) and item.get(field):
                        current[field] = item[field]
                for field in ("aliases", "search_aliases", "related_tags"):
                    merged = list(dict.fromkeys([*(current.get(field) or []), *(item.get(field) or [])]))
                    current[field] = merged[:24]
                current["_search"] = _normalize(
                    " ".join(
                        [
                            current.get("tag", ""),
                            current.get("display_tag", ""),
                            current.get("ja", ""),
                            current.get("description", ""),
                            " ".join(current.get("aliases") or []),
                            " ".join(current.get("search_aliases") or []),
                            " ".join(current.get("related_tags") or []),
                        ]
                    )
                )
            else:
                entries.append(item)

    _CACHE.loaded_at = time.time()
    _CACHE.data_dir = data_dir
    _CACHE.entries = entries
    _CACHE.warning = None
    return entries, _status_from_cache()


def _status_from_cache() -> dict[str, Any]:
    data_dir = _CACHE.data_dir
    return {
        "available": bool(data_dir and _CACHE.entries is not None),
        "data_dir": str(data_dir) if data_dir else None,
        "entry_count": len(_CACHE.entries or []),
        "loaded_at": _CACHE.loaded_at or None,
        "warning": _CACHE.warning,
    }


def prompt_dictionary_status() -> dict[str, Any]:
    entries, status = _load_entries()
    return {
        "ok": True,
        **status,
        "entry_count": len(entries),
        "max_results": MAX_RESULTS,
        "source": "local_tsv",
    }


def _score_entry(entry: dict[str, Any], query: str, tokens: list[str]) -> float:
    tag = _normalize(entry.get("tag"))
    display = _normalize(entry.get("display_tag"))
    ja = _normalize(entry.get("ja"))
    haystack = str(entry.get("_search") or "")
    score = 0.0

    for needle, weight in ((tag, 120), (display, 100), (ja, 95)):
        if not needle:
            continue
        if needle == query:
            score += weight
        elif needle.startswith(query):
            score += weight * 0.72
        elif query in needle:
            score += weight * 0.42

    for token in tokens:
        if token and token in haystack:
            score += 18
    if query and query in haystack:
        score += 35
    if tag == query and "(" not in tag:
        score += 140
    elif tag.startswith(query) and "(" in tag:
        score -= 80
    if "(" in tag and ")" in tag:
        score -= 20
    if entry.get("is_dictionary"):
        score += 8
    if entry.get("has_wiki"):
        score += 3
    if entry.get("is_deprecated"):
        score -= 35

    post_count = max(0, int(entry.get("post_count") or 0))
    if post_count:
        score += min(30, post_count / 200000)
    score += min(12, float(entry.get("importance") or 0) * 3)
    return score


def search_prompt_dictionary(q: str, limit: int = MAX_RESULTS) -> dict[str, Any]:
    entries, status = _load_entries()
    query = _normalize(q)
    max_items = max(1, min(MAX_RESULTS, int(limit or MAX_RESULTS)))
    if not query:
        return {"ok": True, **status, "query": q, "items": [], "count": 0}

    tokens = [part for part in query.split(" ") if part]
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in entries:
        score = _score_entry(entry, query, tokens)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: (-pair[0], -int(pair[1].get("post_count") or 0), str(pair[1].get("tag") or "")))

    items: list[dict[str, Any]] = []
    for score, entry in scored[:max_items]:
        clean = {key: value for key, value in entry.items() if not key.startswith("_")}
        clean["score"] = round(float(score), 3)
        items.append(clean)
    return {"ok": True, **status, "query": q, "items": items, "count": len(items)}
