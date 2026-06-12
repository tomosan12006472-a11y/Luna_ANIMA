from __future__ import annotations

from pathlib import Path
import random
import re
from typing import Any


TOKEN_RE = re.compile(r"__([^\r\n]*?)__")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$")
MAX_DEPTH = 3


def _warning(kind: str, source: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"type": kind, "source": source, "message": message, **extra}


def validate_wildcard_name(name: str) -> tuple[bool, str]:
    text = str(name or "").strip()
    if not text:
        return False, "Wildcard name is empty."
    if "\\" in text or text.startswith("/") or text.endswith("/") or "//" in text:
        return False, f"Invalid wildcard path: {text}"
    if "." in text:
        return False, f"Wildcard names must not include extensions or dots: {text}"
    if not NAME_RE.fullmatch(text):
        return False, f"Wildcard name contains unsupported characters: {text}"
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False, f"Invalid wildcard path segment: {text}"
    return True, ""


def _safe_wildcard_file(base_dir: Path, name: str) -> Path | None:
    rel = Path(*name.split("/")).with_suffix(".txt")
    base = base_dir.resolve()
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def _read_candidates(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _load_candidates(name: str, config_dir: Path, user_dir: Path) -> tuple[list[str], Path | None, str, bool]:
    user_path = _safe_wildcard_file(user_dir, name)
    config_path = _safe_wildcard_file(config_dir, name)
    if user_path and user_path.exists():
        return _read_candidates(user_path), user_path, "user_data", bool(config_path and config_path.exists())
    if config_path and config_path.exists():
        return _read_candidates(config_path), config_path, "config", False
    return [], None, "", False


def _seed_value(seed: Any) -> int:
    try:
        return int(seed)
    except (TypeError, ValueError):
        return 0


def expand_text(
    text: str,
    *,
    rng: random.Random,
    config_dir: Path,
    user_dir: Path,
    selections: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    depth: int = 0,
) -> str:
    if depth > MAX_DEPTH:
        warnings.append(_warning("max_depth", "", f"Dynamic prompt expansion stopped at depth {MAX_DEPTH}."))
        return text

    def replace(match: re.Match[str]) -> str:
        source = match.group(0)
        name = match.group(1).strip()
        valid, reason = validate_wildcard_name(name)
        if not valid:
            warnings.append(_warning("invalid_wildcard", source, reason, name=name))
            return source
        candidates, path, location, overrides_config = _load_candidates(name, config_dir, user_dir)
        if path is None:
            warnings.append(_warning("missing_wildcard", source, f"Wildcard file not found: {name}.txt", name=name))
            return source
        if not candidates:
            warnings.append(_warning("empty_wildcard", source, f"Wildcard file has no candidates: {name}.txt", name=name, file=str(path)))
            return source
        selected = rng.choice(candidates)
        selections.append(
            {
                "type": "wildcard",
                "source": source,
                "name": name,
                "file": str(Path(*name.split("/")).with_suffix(".txt")).replace("\\", "/"),
                "location": location,
                "selected": selected,
                "overrides_config": overrides_config,
            }
        )
        return selected

    expanded = TOKEN_RE.sub(replace, text or "")
    if expanded != (text or "") and TOKEN_RE.search(expanded):
        return expand_text(expanded, rng=rng, config_dir=config_dir, user_dir=user_dir, selections=selections, warnings=warnings, depth=depth + 1)
    return expanded


def expand_dynamic_prompt(
    *,
    positive_prompt: str,
    negative_prompt: str,
    seed: Any,
    enabled: bool,
    config_dir: Path,
    user_dir: Path,
) -> dict[str, Any]:
    wildcard_seed = _seed_value(seed)
    result = {
        "type": "text_file_wildcard",
        "enabled": bool(enabled),
        "wildcard_seed": wildcard_seed,
        "raw_positive_prompt": positive_prompt or "",
        "expanded_positive_prompt": positive_prompt or "",
        "raw_negative_prompt": negative_prompt or "",
        "expanded_negative_prompt": negative_prompt or "",
        "selections": [],
        "warnings": [],
    }
    if not enabled:
        return result
    rng = random.Random(wildcard_seed)
    selections: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    result["expanded_positive_prompt"] = expand_text(
        positive_prompt or "",
        rng=rng,
        config_dir=config_dir,
        user_dir=user_dir,
        selections=selections,
        warnings=warnings,
    )
    result["expanded_negative_prompt"] = expand_text(
        negative_prompt or "",
        rng=rng,
        config_dir=config_dir,
        user_dir=user_dir,
        selections=selections,
        warnings=warnings,
    )
    result["selections"] = selections
    result["warnings"] = warnings
    return result


def _candidate_count(path: Path) -> tuple[int, dict[str, Any] | None]:
    try:
        return len(_read_candidates(path)), None
    except Exception as exc:
        return 0, _warning("read_error", str(path), f"Failed to read wildcard file: {exc}", file=str(path))


def list_wildcards(*, config_dir: Path, user_dir: Path) -> dict[str, Any]:
    items_by_name: dict[str, dict[str, Any]] = {}
    config_names: set[str] = set()
    warnings: list[dict[str, Any]] = []

    for source, base in (("config", config_dir), ("user_data", user_dir)):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.txt")):
            try:
                rel = path.resolve().relative_to(base.resolve())
            except ValueError:
                continue
            name = rel.with_suffix("").as_posix()
            valid, reason = validate_wildcard_name(name)
            if not valid:
                warnings.append(_warning("invalid_wildcard_file", name, reason, file=str(path)))
                continue
            count, read_warning = _candidate_count(path)
            if read_warning:
                warnings.append(read_warning)
            if source == "config":
                config_names.add(name)
            if source == "config" and name in items_by_name:
                continue
            if source == "user_data" or name not in items_by_name:
                items_by_name[name] = {
                    "name": name,
                    "file": rel.as_posix(),
                    "source": source,
                    "count": count,
                    "overrides_config": source == "user_data" and name in config_names,
                }
            if count == 0:
                warnings.append(_warning("empty_wildcard", f"__{name}__", f"Wildcard file has no candidates: {rel.as_posix()}", name=name, file=str(path)))

    return {"items": sorted(items_by_name.values(), key=lambda item: item["name"]), "warnings": warnings}
