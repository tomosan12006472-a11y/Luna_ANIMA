from __future__ import annotations

import os
from typing import Any

from .catalog import SLOT_DEFAULTS, load_catalog
from .discovery import discovery_counts
from .paths import CATALOG_PATH, lora_dirs


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
