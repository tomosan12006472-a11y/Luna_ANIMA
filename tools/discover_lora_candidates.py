from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "lora_discovery_fate_filter.json"
USER_DATA_DIR = REPO_ROOT / "user_data"
DISCOVERY_DIR = USER_DATA_DIR / "lora_discovery"
CACHE_DIR = DISCOVERY_DIR / "cache"
SAA_CSV_PATH = Path(os.environ.get("SAA_WAI_CHARACTERS_CSV", r"D:\AI\character_select_stand_alone_app\data\wai_characters.csv"))
COMFYUI_LORA_DIR = Path(os.environ.get("COMFYUI_LORA_DIR", r"D:\AI\ComfyUI\models\loras"))


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_config() -> dict[str, Any]:
    return load_json(CONFIG_PATH, {})


def norm(value: str) -> str:
    return value.casefold().replace("_", " ").replace("-", " ").strip()


def row_text(row: list[str]) -> str:
    return " | ".join(str(item or "") for item in row)


def fate_match(row: list[str], config: dict[str, Any], index: int) -> tuple[bool, list[str], list[str]]:
    text = norm(row_text(row))
    reasons: list[str] = []
    skips: list[str] = []
    manual_id = f"saa_csv_{index}"
    for term in config.get("manual_exclude") or []:
        if norm(str(term)) in text or str(term) == manual_id:
            return False, [], [f"manual_exclude:{term}"]
    for term in config.get("exclude_terms") or []:
        if norm(str(term)) in text:
            skips.append(f"exclude:{term}")
    if skips:
        return False, [], skips
    for term in config.get("manual_include") or []:
        if norm(str(term)) in text or str(term) == manual_id:
            reasons.append(f"manual_include:{term}")
    for term in config.get("include_terms") or []:
        if norm(str(term)) in text:
            reasons.append(f"include:{term}")
    for term in config.get("weak_terms") or []:
        if norm(str(term)) in text:
            reasons.append(f"weak:{term}")
    strong = any(reason.startswith(("include:", "manual_include:")) for reason in reasons)
    return strong, reasons, skips


def parse_character(row: list[str], index: int, reasons: list[str]) -> dict[str, Any]:
    display_name = row[0].strip() if row else f"row {index}"
    tag_name = row[1].strip() if len(row) > 1 else display_name
    series = ""
    if "(" in tag_name and ")" in tag_name:
        series = tag_name[tag_name.rfind("(") + 1 : tag_name.rfind(")")].strip()
    aliases = [value.strip() for value in row[2:] if value.strip()]
    return {
        "character_id": f"saa_csv_{index}",
        "name": tag_name,
        "jp_name": display_name,
        "series": series,
        "aliases": aliases,
        "source_row": index,
        "source_columns": row,
        "match_reasons": reasons,
    }


def extract_fate_characters(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    characters: list[dict[str, Any]] = []
    stats = {"rows": 0, "matched": 0, "excluded": 0}
    with SAA_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for index, row in enumerate(reader, start=1):
            if not row:
                continue
            stats["rows"] += 1
            matched, reasons, skips = fate_match(row, config, index)
            if skips:
                stats["excluded"] += 1
            if matched:
                stats["matched"] += 1
                characters.append(parse_character(row, index, reasons))
    return characters, stats


def build_queries(character: dict[str, Any], max_queries: int) -> list[str]:
    base_names = []
    for value in [character.get("name"), character.get("jp_name"), *(character.get("aliases") or [])]:
        value = str(value or "").strip()
        if value and value not in base_names:
            base_names.append(value)
    queries: list[str] = []
    for name in base_names:
        queries.extend(
            [
                f'{name} Fate LoRA',
                f'{name} FGO LoRA',
                f'{name} SDXL LoRA',
                f'{name} Illustrious LoRA',
                f'{name} Pony LoRA',
            ]
        )
    unique: list[str] = []
    for query in queries:
        if query not in unique:
            unique.append(query)
    return unique[:max_queries]


def cache_key(source: str, query: str) -> Path:
    digest = hashlib.sha256(f"{source}:{query}".encode("utf-8")).hexdigest()
    return CACHE_DIR / source / f"{digest}.json"


def cached_get_json(source: str, query: str, url: str, headers: dict[str, str], timeout: int = 20) -> tuple[Any, str]:
    path = cache_key(source, query)
    cached = load_json(path, None)
    if cached is not None:
        return cached, "cache"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        data = {"error": f"http_{exc.code}", "status": exc.code}
    except URLError as exc:
        data = {"error": "url_error", "message": str(exc)}
    except Exception as exc:
        data = {"error": "request_failed", "message": str(exc)}
    write_json(path, data)
    return data, "network"


def civitai_search(query: str, limit: int) -> list[dict[str, Any]]:
    params = urlencode({"query": query, "types": "LORA", "limit": limit, "nsfw": "false"})
    url = f"https://civitai.com/api/v1/models?{params}"
    token = os.environ.get("CIVITAI_API_TOKEN")
    headers = {"User-Agent": "MobilePanel-LoRA-Discovery/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data, source = cached_get_json("civitai", query, url, headers)
    items = data.get("items") if isinstance(data, dict) else []
    results: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        version = (item.get("modelVersions") or [{}])[0] if isinstance(item.get("modelVersions"), list) else {}
        files = version.get("files") if isinstance(version, dict) else []
        first_file = files[0] if files else {}
        results.append(
            {
                "source": "civitai",
                "model_id": item.get("id"),
                "model_name": item.get("name") or "",
                "model_type": item.get("type") or "",
                "base_model": version.get("baseModel") if isinstance(version, dict) else "unknown",
                "url": f"https://civitai.com/models/{item.get('id')}" if item.get("id") else "",
                "download_url": None,
                "creator": (item.get("creator") or {}).get("username") if isinstance(item.get("creator"), dict) else None,
                "license": item.get("license") or "unknown",
                "nsfw": bool(item.get("nsfw")),
                "gated": False,
                "file_format": Path(str(first_file.get("name") or "")).suffix.lower().lstrip(".") if isinstance(first_file, dict) else "",
                "file_size": first_file.get("sizeKB") if isinstance(first_file, dict) else None,
                "trained_words": version.get("trainedWords") or [] if isinstance(version, dict) else [],
                "tags": item.get("tags") or [],
                "thumbnail": ((version.get("images") or [{}])[0].get("url") if isinstance(version.get("images"), list) and version.get("images") else None) if isinstance(version, dict) else None,
                "stats": item.get("stats") or {},
                "cache_source": source,
            }
        )
    return results


def huggingface_search(query: str, limit: int) -> list[dict[str, Any]]:
    params = urlencode({"search": query, "limit": limit})
    url = f"https://huggingface.co/api/models?{params}"
    token = os.environ.get("HF_TOKEN")
    headers = {"User-Agent": "MobilePanel-LoRA-Discovery/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data, source = cached_get_json("huggingface", query, url, headers)
    items = data if isinstance(data, list) else []
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("modelId") or item.get("id") or ""
        tags = item.get("tags") or []
        siblings = item.get("siblings") or []
        file_names = [entry.get("rfilename") for entry in siblings if isinstance(entry, dict)]
        safetensors = [name for name in file_names if str(name).lower().endswith(".safetensors")]
        results.append(
            {
                "source": "huggingface",
                "model_id": model_id,
                "model_name": model_id,
                "model_type": "LORA" if any("lora" in norm(str(tag)) for tag in tags) else "unknown",
                "base_model": "unknown",
                "url": f"https://huggingface.co/{model_id}" if model_id else "",
                "download_url": None,
                "creator": str(model_id).split("/")[0] if "/" in str(model_id) else None,
                "license": next((str(tag).removeprefix("license:") for tag in tags if str(tag).startswith("license:")), "unknown"),
                "nsfw": any("nsfw" in norm(str(tag)) for tag in tags),
                "gated": bool(item.get("gated")),
                "file_format": "safetensors" if safetensors else "",
                "file_size": None,
                "trained_words": [],
                "tags": tags,
                "thumbnail": None,
                "stats": {"downloads": item.get("downloads"), "likes": item.get("likes")},
                "cache_source": source,
            }
        )
    return results


def local_search(query: str, limit: int) -> list[dict[str, Any]]:
    words = [part for part in norm(query).split() if len(part) >= 3 and part not in {"lora", "fate", "fgo", "sdxl", "pony"}]
    results: list[dict[str, Any]] = []
    if not COMFYUI_LORA_DIR.exists():
        return results
    for path in sorted(COMFYUI_LORA_DIR.rglob("*.safetensors")):
        text = norm(str(path.relative_to(COMFYUI_LORA_DIR)))
        if words and not any(word in text for word in words):
            continue
        results.append(
            {
                "source": "local",
                "model_id": str(path),
                "model_name": path.stem,
                "model_type": "LORA",
                "base_model": "ANIMA" if path.name.lower().startswith("anima-") else "unknown",
                "url": str(path),
                "download_url": None,
                "creator": None,
                "license": "local",
                "nsfw": False,
                "gated": False,
                "file_format": "safetensors",
                "file_size": path.stat().st_size,
                "trained_words": [],
                "tags": ["local"],
                "thumbnail": None,
                "stats": {},
                "cache_source": "local",
            }
        )
        if len(results) >= limit:
            break
    return results


def score_candidate(character: dict[str, Any], candidate: dict[str, Any], app: str) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    risk_flags: list[str] = []
    haystack = norm(" ".join([str(candidate.get("model_name") or ""), " ".join(candidate.get("tags") or []), " ".join(candidate.get("trained_words") or [])]))
    names = [character.get("name"), character.get("jp_name"), *(character.get("aliases") or [])]
    if any(norm(str(name)) and norm(str(name)) in haystack for name in names):
        score += 40
        reasons.append("character name matched")
    if any(term in haystack for term in ["fate", "fgo", "grand order"]):
        score += 20
        reasons.append("Fate term matched")
    if norm(str(candidate.get("model_type"))) == "lora":
        score += 20
        reasons.append("model type appears to be LoRA")
    base = norm(str(candidate.get("base_model") or ""))
    if app == "saa" and any(term in base for term in ["sdxl", "pony", "illustrious", "wai"]):
        score += 15
        reasons.append("base model appears SAA compatible")
    if app == "anima" and "anima" in base:
        score += 15
        reasons.append("base model appears ANIMA compatible")
    if candidate.get("file_format") == "safetensors":
        score += 5
        reasons.append("safetensors file")
    if candidate.get("nsfw"):
        score -= 40
        risk_flags.append("nsfw")
    if candidate.get("gated"):
        score -= 30
        risk_flags.append("gated")
    if candidate.get("license") in {None, "", "unknown"}:
        score -= 10
        risk_flags.append("license_unknown")
    if app == "anima" and any(term in base for term in ["sdxl", "pony", "illustrious", "wai"]):
        score -= 60
        risk_flags.append("base_model_mismatch")
    if candidate.get("model_type") and norm(str(candidate.get("model_type"))) != "lora":
        score -= 80
        risk_flags.append("not_lora")
    if risk_flags and any(flag in risk_flags for flag in ["nsfw", "gated", "not_lora"]):
        status = "blocked"
    elif score >= 80:
        status = "strong_candidate"
    elif score >= 50:
        status = "review_required"
    elif score > 0:
        status = "weak_candidate"
    else:
        status = "rejected_by_score"
    return {"score": score, "status": status, "reason": reasons, "risk_flags": risk_flags}


def discover_candidates(characters: list[dict[str, Any]], args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    sources = [source.strip() for source in args.sources.split(",") if source.strip()]
    max_queries = int(args.max_queries_per_character or config.get("max_queries_per_character") or 3)
    max_candidates = int(args.max_candidates_per_query or config.get("max_candidates_per_query") or 5)
    sleep_seconds = float(args.sleep_seconds if args.sleep_seconds is not None else config.get("sleep_seconds", 0.3))
    output_characters: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for character in characters:
        char_out = dict(character)
        char_out["queries"] = build_queries(character, max_queries)
        char_out["candidates"] = []
        for query in char_out["queries"]:
            source_results: list[dict[str, Any]] = []
            if "local" in sources:
                source_results.extend(local_search(query, max_candidates))
            if not args.no_network and "civitai" in sources:
                source_results.extend(civitai_search(query, max_candidates))
                time.sleep(sleep_seconds)
            if not args.no_network and "huggingface" in sources:
                source_results.extend(huggingface_search(query, max_candidates))
                time.sleep(sleep_seconds)
            for raw in source_results:
                url = str(raw.get("url") or raw.get("model_id") or "")
                if url and url in seen_urls:
                    continue
                seen_urls.add(url)
                scoring = score_candidate(character, raw, args.app)
                candidate = {
                    "candidate_id": f"{raw.get('source')}_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}",
                    **raw,
                    **scoring,
                    "app_scope_suggestion": args.app if scoring["status"] != "blocked" else "unknown",
                    "category_suggestion": "character",
                    "query": query,
                }
                char_out["candidates"].append(candidate)
        output_characters.append(char_out)
    return {
        "schema_version": 1,
        "scope": args.scope,
        "generated_at": now_iso(),
        "dry_run": True,
        "sources": sources,
        "characters": output_characters,
    }


def write_report(characters: list[dict[str, Any]], candidates: dict[str, Any] | None, stats: dict[str, int], args: argparse.Namespace) -> None:
    lines = [
        "# Fate LoRA Discovery Report",
        "",
        f"- generated_at: {now_iso()}",
        f"- csv: {SAA_CSV_PATH}",
        f"- rows: {stats['rows']}",
        f"- fate_characters: {len(characters)}",
        f"- dry_run: true",
        f"- sources: {args.sources}",
        f"- no_network: {args.no_network}",
        "",
    ]
    if candidates:
        total = sum(len(character.get("candidates") or []) for character in candidates.get("characters") or [])
        blocked = sum(1 for character in candidates.get("characters") or [] for candidate in character.get("candidates") or [] if candidate.get("status") == "blocked")
        review = sum(1 for character in candidates.get("characters") or [] for candidate in character.get("candidates") or [] if candidate.get("status") == "review_required")
        lines.extend([f"- candidates: {total}", f"- blocked: {blocked}", f"- review_required: {review}", ""])
    lines.append("## Characters")
    for character in characters[:200]:
        lines.append(f"- {character['character_id']}: {character['jp_name']} / {character['name']} / {character.get('series') or '-'}")
    (DISCOVERY_DIR / "fate_discovery_report.md").write_text("\n".join(lines), encoding="utf-8")
    (DISCOVERY_DIR / "fate_character_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="fate", choices=["fate"])
    parser.add_argument("--app", default="saa", choices=["saa", "anima"])
    parser.add_argument("--extract-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--limit-characters", type=int, default=None)
    parser.add_argument("--max-queries-per-character", type=int, default=None)
    parser.add_argument("--max-candidates-per-query", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=None)
    parser.add_argument("--sources", default="local,civitai,huggingface")
    parser.add_argument("--no-network", action="store_true")
    args = parser.parse_args()

    config = load_config()
    characters, stats = extract_fate_characters(config)
    limit = args.limit_characters
    if limit is None:
        limit = int(config.get("max_characters") or 100)
    selected = characters if limit == 0 else characters[: max(0, limit)]

    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    character_data = {
        "schema_version": 1,
        "scope": args.scope,
        "generated_at": now_iso(),
        "csv": str(SAA_CSV_PATH),
        "stats": stats,
        "characters": characters,
    }
    write_json(DISCOVERY_DIR / "fate_characters.json", character_data)

    candidates = None
    if not args.extract_only:
        candidates = discover_candidates(selected, args, config)
        write_json(DISCOVERY_DIR / "fate_candidates_raw.json", candidates)
        write_json(DISCOVERY_DIR / "fate_candidates_normalized.json", candidates)
        review_items = []
        for character in candidates["characters"]:
            for candidate in character.get("candidates") or []:
                if candidate.get("status") in {"strong_candidate", "review_required"}:
                    review_items.append({"character_id": character["character_id"], **candidate, "review_status": "hold"})
        write_json(DISCOVERY_DIR / "fate_review_queue.json", {"schema_version": 1, "scope": args.scope, "generated_at": now_iso(), "items": review_items})

    write_report(selected, candidates, stats, args)
    print(json.dumps({"ok": True, "fate_characters": len(characters), "selected_characters": len(selected), "candidate_characters": len(candidates["characters"]) if candidates else 0, "downloaded": 0, "discovery_dir": str(DISCOVERY_DIR)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
