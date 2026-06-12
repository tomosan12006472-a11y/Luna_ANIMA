from __future__ import annotations

from threading import Lock
import time
from typing import Any

from . import comfy_client
from .config import COMFYUI_ADDR_DEFAULT


MODEL_INFO_CACHE_TTL_SECONDS = 60
_MODEL_INFO_CACHE: dict[str, dict[str, Any]] = {}
_MODEL_INFO_CACHE_LOCK = Lock()


def _object_choice(info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    value = info.get(class_name, {}).get("input", {}).get("required", {}).get(input_name, [[]])
    if isinstance(value, list) and value and isinstance(value[0], list):
        return [str(item) for item in value[0]]
    if isinstance(value, list) and len(value) > 1 and isinstance(value[1], dict) and isinstance(value[1].get("options"), list):
        return [str(item) for item in value[1]["options"]]
    return []


def model_cache_status(addr: str) -> dict[str, Any]:
    with _MODEL_INFO_CACHE_LOCK:
        cached = _MODEL_INFO_CACHE.get(addr)
    if not cached:
        return {"hit": False, "stale": False, "age_sec": None, "ttl_sec": MODEL_INFO_CACHE_TTL_SECONDS}
    age = max(0.0, time.monotonic() - float(cached.get("stored_at") or 0))
    return {
        "hit": age <= MODEL_INFO_CACHE_TTL_SECONDS,
        "stale": age > MODEL_INFO_CACHE_TTL_SECONDS,
        "age_sec": round(age, 3),
        "ttl_sec": MODEL_INFO_CACHE_TTL_SECONDS,
    }


def cached_object_info(addr: str, refresh: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    cache_key = addr or COMFYUI_ADDR_DEFAULT
    with _MODEL_INFO_CACHE_LOCK:
        cached = _MODEL_INFO_CACHE.get(cache_key)
    age = time.monotonic() - float(cached.get("stored_at") or 0) if cached else None
    if cached and not refresh and age is not None and age <= MODEL_INFO_CACHE_TTL_SECONDS:
        return cached["info"], {**model_cache_status(cache_key), "refreshed": False}
    try:
        info = comfy_client.object_info(cache_key)
    except Exception as exc:
        if cached:
            return cached["info"], {**model_cache_status(cache_key), "hit": True, "stale": True, "refreshed": False, "error": str(exc)}
        raise
    with _MODEL_INFO_CACHE_LOCK:
        _MODEL_INFO_CACHE[cache_key] = {"stored_at": time.monotonic(), "info": info}
    return info, {**model_cache_status(cache_key), "hit": False, "stale": False, "refreshed": True}
