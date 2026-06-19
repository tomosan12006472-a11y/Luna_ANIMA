from __future__ import annotations

import re
from pathlib import Path

from ..config import COMFYUI_LORA_DIRS, USER_DATA_DIR


APP_SCOPE = "anima"
CATALOG_PATH = USER_DATA_DIR / "lora_catalog_anima.json"
FAVORITES_PATH = USER_DATA_DIR / "lora_favorites_anima.json"
DISCOVERY_DIR = USER_DATA_DIR / "lora_discovery"


def slug(value: str) -> str:
    slug_value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return slug_value[:80] or "lora"


def safe_relative(path: Path, root: Path) -> str:
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


_slug = slug
_safe_relative = safe_relative
