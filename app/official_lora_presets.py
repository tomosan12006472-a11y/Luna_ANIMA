from __future__ import annotations

from copy import deepcopy
from typing import Any

from ._shared_utils import clamp_strength


BUILTIN_OFFICIAL_LORA_PRESETS: dict[str, dict[str, Any]] = {
    "off": {
        "id": "off",
        "title": "OFF",
        "note": "Disable all official LoRAs.",
        "official_loras": {
            "highres": {"enabled": False, "strength": 0.6},
            "turbo": {"enabled": False, "version": "auto", "strength": 0.6, "preset_applied": False},
            "colorfix": {"enabled": False, "strength": 0.6},
        },
    },
    "color_stable": {
        "id": "color_stable",
        "title": "Color Stable",
        "note": "Use ColorFix only for color tone stability.",
        "official_loras": {
            "highres": {"enabled": False, "strength": 0.6},
            "turbo": {"enabled": False, "version": "auto", "strength": 0.6, "preset_applied": False},
            "colorfix": {"enabled": True, "strength": 0.6},
        },
    },
    "quality": {
        "id": "quality",
        "title": "Quality",
        "note": "Use Highres and ColorFix for regular quality output.",
        "official_loras": {
            "highres": {"enabled": True, "strength": 0.6},
            "turbo": {"enabled": False, "version": "auto", "strength": 0.6, "preset_applied": False},
            "colorfix": {"enabled": True, "strength": 0.6},
        },
    },
    "fast_preview": {
        "id": "fast_preview",
        "title": "Fast Preview",
        "note": "Use Turbo and recommended fast preview settings.",
        "official_loras": {
            "highres": {"enabled": False, "strength": 0.6},
            "turbo": {"enabled": True, "version": "auto", "strength": 1.0, "preset_applied": True},
            "colorfix": {"enabled": False, "strength": 0.6},
        },
    },
    "fast_color": {
        "id": "fast_color",
        "title": "Fast Color",
        "note": "Use Turbo plus ColorFix for quick color-stable previews.",
        "official_loras": {
            "highres": {"enabled": False, "strength": 0.6},
            "turbo": {"enabled": True, "version": "auto", "strength": 1.0, "preset_applied": True},
            "colorfix": {"enabled": True, "strength": 0.6},
        },
    },
    "final_quality": {
        "id": "final_quality",
        "title": "Final Quality",
        "note": "Use Highres and ColorFix for final output.",
        "official_loras": {
            "highres": {"enabled": True, "strength": 0.6},
            "turbo": {"enabled": False, "version": "auto", "strength": 0.6, "preset_applied": False},
            "colorfix": {"enabled": True, "strength": 0.6},
        },
    },
}


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "off", "no", "disabled"}
    return bool(value)


def official_lora_preset_ids() -> list[str]:
    return list(BUILTIN_OFFICIAL_LORA_PRESETS)


def normalize_official_lora_preset_id(value: Any) -> str:
    preset_id = str(value or "").strip()
    if not preset_id:
        return "off"
    return preset_id if preset_id in BUILTIN_OFFICIAL_LORA_PRESETS or preset_id == "custom" else "custom"


def builtin_official_lora_presets() -> list[dict[str, Any]]:
    return [deepcopy(item) for item in BUILTIN_OFFICIAL_LORA_PRESETS.values()]


def apply_builtin_official_lora_preset(preset_id: str) -> dict[str, Any]:
    if preset_id not in BUILTIN_OFFICIAL_LORA_PRESETS:
        raise KeyError(f"Unknown official LoRA preset: {preset_id}")
    return deepcopy(BUILTIN_OFFICIAL_LORA_PRESETS[preset_id]["official_loras"])


def sanitize_official_loras(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    highres = raw.get("highres") if isinstance(raw.get("highres"), dict) else {}
    turbo = raw.get("turbo") if isinstance(raw.get("turbo"), dict) else {}
    colorfix = raw.get("colorfix") if isinstance(raw.get("colorfix"), dict) else {}
    return {
        "highres": {
            "enabled": _bool_value(highres.get("enabled")),
            "strength": clamp_strength(highres.get("strength"), 0.6),
        },
        "turbo": {
            "enabled": _bool_value(turbo.get("enabled")),
            "version": str(turbo.get("version") or "auto"),
            "strength": clamp_strength(turbo.get("strength"), 0.6),
            "preset_applied": _bool_value(turbo.get("preset_applied", True)),
        },
        "colorfix": {
            "enabled": _bool_value(colorfix.get("enabled")),
            "strength": clamp_strength(colorfix.get("strength"), 0.6),
        },
    }


def infer_builtin_official_lora_preset_id(value: Any) -> str:
    def comparable(data: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(data)
        turbo = result.get("turbo") if isinstance(result.get("turbo"), dict) else {}
        if not turbo.get("enabled"):
            turbo["preset_applied"] = False
            result["turbo"] = turbo
        return result

    official = comparable(sanitize_official_loras(value))
    for preset_id, preset in BUILTIN_OFFICIAL_LORA_PRESETS.items():
        candidate = comparable(sanitize_official_loras(preset.get("official_loras")))
        if official == candidate:
            return preset_id
    return "custom"
