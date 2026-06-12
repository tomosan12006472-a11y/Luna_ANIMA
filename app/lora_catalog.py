from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from ._shared_utils import clamp_strength
from .config import (
    ANIMA_HIGHRES_LORA_NAME,
    ANIMA_TURBO_LORA_V01_NAME,
    ANIMA_TURBO_LORA_V02_NAME,
    COMFYUI_LORA_DIRS,
    USER_DATA_DIR,
)


APP_SCOPE = "anima"
CATALOG_PATH = USER_DATA_DIR / "lora_catalog_anima.json"
FAVORITES_PATH = USER_DATA_DIR / "lora_favorites_anima.json"
DISCOVERY_DIR = USER_DATA_DIR / "lora_discovery"

SLOT_DEFAULTS: dict[str, dict[str, Any]] = {
    "character": {"enabled": False, "lora_id": "none", "model_strength": 0.70, "clip_strength": 0.70, "max_strength": 1.0},
    "style": {"enabled": False, "lora_id": "none", "model_strength": 0.25, "clip_strength": 0.25, "max_strength": 1.0},
    "official_hires": {"enabled": False, "lora_id": "none", "model_strength": 0.60, "clip_strength": 0.60, "max_strength": 1.00},
    "turbo": {"enabled": False, "lora_id": "none", "model_strength": 0.60, "clip_strength": 0.60, "max_strength": 1.00},
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return slug[:80] or "lora"


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return path.name


def lora_dirs() -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for directory in COMFYUI_LORA_DIRS:
        key = str(directory)
        if key not in seen:
            seen.add(key)
            result.append(directory)
    return result


def _category_for_name(file_name: str) -> str:
    lower = file_name.lower()
    if lower == ANIMA_HIGHRES_LORA_NAME.lower():
        return "hires"
    if lower in {ANIMA_TURBO_LORA_V01_NAME.lower(), ANIMA_TURBO_LORA_V02_NAME.lower()}:
        return "turbo"
    if lower.startswith("anima-"):
        return "official"
    return "unknown"


def scan_local_loras() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for directory in lora_dirs():
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.safetensors")):
            relative_path = _safe_relative(path, directory)
            key = relative_path.lower()
            if key in seen:
                continue
            seen.add(key)
            lower_name = path.name.lower()
            parts = [part.lower() for part in Path(relative_path).parts]
            is_anima = lower_name.startswith("anima-") or "anima" in parts
            app_scope = "anima" if is_anima else "unknown"
            category = _category_for_name(path.name)
            items.append(
                {
                    "lora_id": f"{APP_SCOPE}_local_{_slug(relative_path)}",
                    "display_name": path.stem,
                    "file_name": path.name,
                    "relative_path": relative_path,
                    "app_scope": app_scope,
                    "category": category,
                    "base_model": "ANIMA" if is_anima else "unknown",
                    "source": "local",
                    "source_url": None,
                    "creator": None,
                    "license": None,
                    "nsfw": False,
                    "rating": "unknown",
                    "trained_words": [],
                    "default_model_strength": 0.6 if category in {"hires", "turbo"} else 0.7,
                    "default_clip_strength": 0.0,
                    "max_strength": 1.0,
                    "thumbnail": None,
                    "sha256": None,
                    "status": "available" if is_anima else "review_required",
                    "notes": "Local ComfyUI LoRA scan",
                }
            )
    return items


def default_catalog() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "app_scope": APP_SCOPE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": scan_local_loras(),
    }


def load_catalog() -> dict[str, Any]:
    if not CATALOG_PATH.exists():
        return default_catalog()
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return default_catalog()
    if not isinstance(data, dict):
        return default_catalog()
    items = data.get("items")
    if not isinstance(items, list):
        data["items"] = []
    else:
        for item in items:
            if isinstance(item, dict):
                item["max_strength"] = 1.0
    data.setdefault("schema_version", 1)
    data.setdefault("app_scope", APP_SCOPE)
    return data


def refresh_catalog() -> dict[str, Any]:
    catalog = default_catalog()
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog


def _favorite_identity(item: dict[str, Any]) -> str:
    for key in ("lora_id", "relative_path", "file_name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _favorite_match_keys(item: dict[str, Any]) -> set[str]:
    return {str(item.get(key) or "").strip() for key in ("lora_id", "relative_path", "file_name") if str(item.get(key) or "").strip()}


def load_lora_favorites() -> dict[str, Any]:
    if not FAVORITES_PATH.exists():
        return {"schema_version": 1, "app_scope": APP_SCOPE, "favorites": {}}
    try:
        data = json.loads(FAVORITES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 1, "app_scope": APP_SCOPE, "favorites": {}}
    if not isinstance(data, dict) or data.get("app_scope") != APP_SCOPE:
        return {"schema_version": 1, "app_scope": APP_SCOPE, "favorites": {}}
    favorites = data.get("favorites")
    if not isinstance(favorites, dict):
        data["favorites"] = {}
    data.setdefault("schema_version", 1)
    data.setdefault("app_scope", APP_SCOPE)
    return data


def write_lora_favorites(data: dict[str, Any]) -> None:
    data["schema_version"] = 1
    data["app_scope"] = APP_SCOPE
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    FAVORITES_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAVORITES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def favorite_key_set(data: dict[str, Any] | None = None) -> set[str]:
    source = data or load_lora_favorites()
    keys: set[str] = set()
    for key, item in (source.get("favorites") or {}).items():
        if isinstance(key, str) and key:
            keys.add(key)
        if isinstance(item, dict):
            keys.update(_favorite_match_keys(item))
    return keys


def catalog_with_favorites(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    data = deepcopy(catalog or load_catalog())
    favorite_data = load_lora_favorites()
    keys = favorite_key_set(favorite_data)
    favorites = favorite_data.get("favorites") or {}
    favorite_count = 0
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        item_keys = _favorite_match_keys(item)
        favorite = bool(item_keys & keys)
        item["favorite"] = favorite
        if favorite:
            favorite_count += 1
            matched = next((favorites.get(key) for key in item_keys if isinstance(favorites.get(key), dict)), None)
            if matched:
                item["favorite_added_at"] = matched.get("added_at", "")
    data["favorite_count"] = favorite_count
    return data


def _is_selectable(item: dict[str, Any]) -> bool:
    return item.get("app_scope") == APP_SCOPE and item.get("status") == "available"


def selectable_loras(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = catalog_with_favorites(catalog)
    return [deepcopy(item) for item in data.get("items", []) if isinstance(item, dict) and _is_selectable(item)]


def find_selectable_lora(query: dict[str, Any]) -> dict[str, Any] | None:
    query_keys = _favorite_match_keys(query)
    for item in selectable_loras():
        if _favorite_match_keys(item) & query_keys:
            return item
    return None


def list_lora_favorites() -> dict[str, Any]:
    data = load_lora_favorites()
    selectable = selectable_loras()
    available_keys = set().union(*(_favorite_match_keys(item) for item in selectable)) if selectable else set()
    items: list[dict[str, Any]] = []
    for key, favorite in (data.get("favorites") or {}).items():
        if not isinstance(favorite, dict):
            continue
        record = deepcopy(favorite)
        record.setdefault("lora_id", key)
        record["available"] = bool(_favorite_match_keys(record) & available_keys)
        items.append(record)
    return {"ok": True, **data, "items": items, "favorite_count": len(items)}


def set_lora_favorite(query: dict[str, Any], favorite: bool | None = None) -> dict[str, Any]:
    data = load_lora_favorites()
    favorites = data.setdefault("favorites", {})
    query_keys = _favorite_match_keys(query)
    existing_keys = [key for key, item in favorites.items() if key in query_keys or (isinstance(item, dict) and _favorite_match_keys(item) & query_keys)]
    currently_favorite = bool(existing_keys)
    desired = (not currently_favorite) if favorite is None else bool(favorite)

    if not desired:
        for key in existing_keys:
            favorites.pop(key, None)
        write_lora_favorites(data)
        return {"ok": True, "favorite": False, "removed": bool(existing_keys), **list_lora_favorites()}

    item = find_selectable_lora(query)
    if item is None:
        return {"ok": False, "favorite": False, "status": "not_selectable", "message": "LoRA is not selectable for this app scope."}
    key = _favorite_identity(item)
    if not key:
        return {"ok": False, "favorite": False, "status": "missing_identity", "message": "LoRA does not have a stable identity."}
    now = datetime.now().isoformat(timespec="seconds")
    favorites[key] = {
        "lora_id": item.get("lora_id", ""),
        "relative_path": item.get("relative_path", ""),
        "file_name": item.get("file_name", ""),
        "display_name": item.get("display_name") or item.get("file_name") or item.get("lora_id") or key,
        "app_scope": APP_SCOPE,
        "added_at": (favorites.get(key, {}).get("added_at") if isinstance(favorites.get(key), dict) else "") or now,
    }
    write_lora_favorites(data)
    response = list_lora_favorites()
    response.update({"favorite": True, "item": favorites[key]})
    return response


def normalize_lora_slots(loras: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    catalog_items = {str(item.get("lora_id")): item for item in selectable_loras()}
    normalized: list[dict[str, Any]] = []
    for raw in loras or []:
        if not isinstance(raw, dict):
            continue
        enabled = bool(raw.get("enabled", True))
        mode = str(raw.get("mode") or "ALL")
        lora_id = str(raw.get("lora_id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not enabled or mode == "OFF" or lora_id == "none":
            continue
        source = "manual"
        display_name = name
        relative_path = name
        app_scope = APP_SCOPE
        category = str(raw.get("category") or "unknown")
        if lora_id and lora_id in catalog_items:
            item = catalog_items[lora_id]
            source = "catalog"
            display_name = str(item.get("display_name") or item.get("file_name") or lora_id)
            relative_path = str(item.get("relative_path") or item.get("file_name") or "")
            app_scope = str(item.get("app_scope") or APP_SCOPE)
            category = str(item.get("category") or category)
        elif not name:
            continue
        legacy_strength = clamp_strength(raw.get("weight", raw.get("strength", raw.get("model_strength", raw.get("model", 1.0)))), 1.0)
        model_strength = clamp_strength(raw.get("strength_model", raw.get("model_strength", raw.get("model_weight", raw.get("weight_model", raw.get("model", legacy_strength))))), legacy_strength)
        clip_strength = clamp_strength(raw.get("strength_clip", raw.get("clip_strength", raw.get("clip_weight", raw.get("weight_clip", raw.get("clip", legacy_strength))))), legacy_strength)
        normalized.append(
            {
                "slot": str(raw.get("slot") or "custom"),
                "enabled": True,
                "lora_id": lora_id or _slug(relative_path),
                "display_name": display_name,
                "name": relative_path,
                "relative_path": relative_path,
                "model": model_strength,
                "clip": clip_strength,
                "model_strength": model_strength,
                "clip_strength": clip_strength,
                "strength_model": model_strength,
                "strength_clip": clip_strength,
                "weight": model_strength,
                "mode": mode,
                "app_scope": app_scope,
                "category": category,
                "source": source,
            }
        )
    return normalized


def discovery_counts() -> dict[str, Any]:
    result: dict[str, Any] = {
        "fate_character_count": 0,
        "fate_candidate_count": 0,
        "blocked_candidate_count": 0,
        "review_required_count": 0,
        "approved_candidate_count": 0,
        "downloadable_candidate_count": 0,
        "last_discovery_run": None,
    }
    characters_path = DISCOVERY_DIR / "fate_characters.json"
    candidates_path = DISCOVERY_DIR / "fate_candidates_normalized.json"
    review_path = DISCOVERY_DIR / "fate_review_queue.json"
    for path in (characters_path, candidates_path, review_path):
        if path.exists():
            result["last_discovery_run"] = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    if characters_path.exists():
        try:
            characters = json.loads(characters_path.read_text(encoding="utf-8"))
            if isinstance(characters, dict):
                result["fate_character_count"] = len(characters.get("characters") or [])
        except Exception:
            pass
    if candidates_path.exists():
        try:
            data = json.loads(candidates_path.read_text(encoding="utf-8"))
            for character in data.get("characters") or []:
                for candidate in character.get("candidates") or []:
                    result["fate_candidate_count"] += 1
                    status = candidate.get("status")
                    if status == "blocked":
                        result["blocked_candidate_count"] += 1
                    if status == "review_required":
                        result["review_required_count"] += 1
        except Exception:
            pass
    if review_path.exists():
        try:
            data = json.loads(review_path.read_text(encoding="utf-8"))
            for candidate in data.get("items") or []:
                if candidate.get("review_status") in {"approved_anima", "approved"}:
                    result["approved_candidate_count"] += 1
                    if candidate.get("download_url"):
                        result["downloadable_candidate_count"] += 1
        except Exception:
            pass
    return result


def diagnostics(comfy_loras: list[str] | None = None) -> dict[str, Any]:
    catalog = load_catalog()
    items = [item for item in catalog.get("items", []) if isinstance(item, dict)]
    catalog_paths = {str(item.get("relative_path") or item.get("file_name") or "") for item in items}
    comfy_set = set(comfy_loras or [])
    return {
        "catalog_path": str(CATALOG_PATH),
        "catalog_file_exists": CATALOG_PATH.exists(),
        "catalog_item_count": len(items),
        "saa_compatible_count": sum(1 for item in items if item.get("app_scope") == "saa" and item.get("status") == "available"),
        "anima_compatible_count": sum(1 for item in items if item.get("app_scope") == "anima" and item.get("status") == "available"),
        "local_comfy_lora_count": len(comfy_set),
        "catalog_not_visible_to_comfy": sorted(path for path in catalog_paths if path and comfy_set and path not in comfy_set),
        "comfy_not_in_catalog": sorted(name for name in comfy_set if name not in catalog_paths),
        "lora_dirs": [str(path) for path in lora_dirs()],
        "slot_defaults": SLOT_DEFAULTS,
        "workflow_injection": "ANIMA LoraLoaderModelOnly for official/generic compatible LoRAs",
        "api_tokens": {
            "civitai": bool(os.environ.get("CIVITAI_API_TOKEN")),
            "huggingface": bool(os.environ.get("HF_TOKEN")),
        },
        **discovery_counts(),
    }


def read_discovery_file(name: str) -> dict[str, Any]:
    path = DISCOVERY_DIR / name
    if not path.exists():
        return {"ok": True, "exists": False, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "exists": True, "path": str(path), "error": str(exc)}
    if isinstance(data, dict):
        data.setdefault("ok", True)
        data.setdefault("exists", True)
        data.setdefault("path", str(path))
        return data
    return {"ok": True, "exists": True, "path": str(path), "items": data}


def review_candidate(candidate_id: str, review_status: str, app_scope: str, note: str = "") -> dict[str, Any]:
    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
    path = DISCOVERY_DIR / "fate_review_queue.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {"schema_version": 1, "scope": "fate", "items": []}
    else:
        data = {"schema_version": 1, "scope": "fate", "items": []}
    items = data.setdefault("items", [])
    found = None
    for item in items:
        if item.get("candidate_id") == candidate_id:
            found = item
            break
    if found is None:
        found = {"candidate_id": candidate_id}
        items.append(found)
    found.update(
        {
            "review_status": review_status,
            "app_scope": app_scope,
            "note": note,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "review": found, "path": str(path)}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
