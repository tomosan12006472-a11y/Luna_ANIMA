from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .._shared_utils import LORA_STRENGTH_MAX
from ..config import ANIMA_COLORFIX_LORA_NAME, ANIMA_HIGHRES_LORA_NAME, ANIMA_TURBO_LORA_V01_NAME, ANIMA_TURBO_LORA_V02_NAME
from .paths import APP_SCOPE, lora_dirs, safe_relative, slug


def _configured_file_name(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _category_for_name(file_name: str) -> str:
    lower = file_name.lower()
    if lower == _configured_file_name(ANIMA_HIGHRES_LORA_NAME):
        return "hires"
    if lower in {_configured_file_name(ANIMA_TURBO_LORA_V01_NAME), _configured_file_name(ANIMA_TURBO_LORA_V02_NAME)}:
        return "turbo"
    if lower == _configured_file_name(ANIMA_COLORFIX_LORA_NAME):
        return "colorfix"
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
            relative_path = safe_relative(path, directory)
            key = relative_path.lower()
            if key in seen:
                continue
            seen.add(key)
            lower_name = path.name.lower()
            parts = [part.lower() for part in Path(relative_path).parts]
            is_root_lora = len(parts) == 1
            is_anima = is_root_lora or lower_name.startswith("anima-") or "anima" in parts
            app_scope = "anima" if is_anima else "unknown"
            category = _category_for_name(path.name)
            items.append(
                {
                    "lora_id": f"{APP_SCOPE}_local_{slug(relative_path)}",
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
                    "default_model_strength": 0.6 if category in {"hires", "turbo", "colorfix"} else 0.7,
                    "default_clip_strength": 0.0,
                    "max_strength": LORA_STRENGTH_MAX,
                    "thumbnail": None,
                    "sha256": None,
                    "status": "available" if is_anima else "review_required",
                    "notes": "Local ComfyUI LoRA scan",
                }
            )
    return items


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
