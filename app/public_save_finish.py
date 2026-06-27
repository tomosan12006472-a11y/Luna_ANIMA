from __future__ import annotations

from bisect import bisect_right
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import os

from PIL import Image, ImageChops, ImageEnhance

from ._shared_utils import clamp_float
from .config import ROOT_DIR, USER_DATA_DIR


FINISH_PRESET_ID = "krita_itsumono"
PUBLIC_SAVE_FINISH_DIR = USER_DATA_DIR / "public_save_finish"
PUBLIC_SAVE_FINISH_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_SETTINGS = {
    "finish_enabled": False,
    "finish_preset": FINISH_PRESET_ID,
}


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    for env_name in ("LUNA_KRITA_ITSUMONO_PRESET", "LUNA_PUBLIC_SAVE_FINISH_PRESET"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            paths.append(Path(raw))
    paths.extend(
        [
            USER_DATA_DIR / "public_save_finish" / "krita_itsumono.json",
            USER_DATA_DIR / "krita_itsumono.json",
            USER_DATA_DIR / "krita" / "itsumono.json",
            ROOT_DIR / "config" / "krita_itsumono.example.json",
        ]
    )
    return paths


def sanitize_public_save_finish_settings(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    preset = str(raw.get("finish_preset") or raw.get("preset") or FINISH_PRESET_ID).strip()
    if preset != FINISH_PRESET_ID:
        preset = FINISH_PRESET_ID
    return {
        "finish_enabled": bool(raw.get("finish_enabled", raw.get("enabled", False))),
        "finish_preset": preset,
    }


def public_save_finish_settings_from_app(settings: dict[str, Any] | None) -> dict[str, Any]:
    app_settings = settings if isinstance(settings, dict) else {}
    public_save = app_settings.get("public_save") if isinstance(app_settings.get("public_save"), dict) else {}
    return sanitize_public_save_finish_settings(
        {
            "finish_enabled": public_save.get("finish_enabled", False),
            "finish_preset": public_save.get("finish_preset", FINISH_PRESET_ID),
        }
    )


def resolve_public_save_finish(data: Any, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    finish_enabled = getattr(data, "finish_enabled", None)
    finish_preset = getattr(data, "finish_preset", None)
    if finish_enabled is not None or finish_preset:
        return sanitize_public_save_finish_settings(
            {
                "finish_enabled": bool(finish_enabled),
                "finish_preset": finish_preset or FINISH_PRESET_ID,
            }
        )
    return public_save_finish_settings_from_app(settings)


def _safe_path_label(path: Path | None) -> str:
    if not path:
        return ""
    try:
        if path.resolve().is_relative_to(ROOT_DIR.resolve()):
            return str(path.resolve().relative_to(ROOT_DIR.resolve())).replace("\\", "/")
    except OSError:
        pass
    return path.name


def _read_preset(path: Path) -> tuple[dict[str, Any] | None, str, str]:
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        return None, "", str(exc)
    if not isinstance(data, dict):
        return None, "", "preset root must be an object"
    return data, sha256(raw).hexdigest(), ""


def load_public_save_finish_preset(preset_id: str = FINISH_PRESET_ID) -> dict[str, Any]:
    if preset_id != FINISH_PRESET_ID:
        return {
            "preset": preset_id,
            "configured": False,
            "available": False,
            "operations": [],
            "content_hash": "",
            "path_label": "",
            "warnings": [f"unsupported preset: {preset_id}"],
        }
    warnings: list[str] = []
    for path in _candidate_paths():
        if not path.exists():
            continue
        data, digest, error = _read_preset(path)
        if error:
            return {
                "preset": preset_id,
                "configured": True,
                "available": False,
                "operations": [],
                "content_hash": "",
                "path_label": _safe_path_label(path),
                "warnings": [error],
            }
        if path.name.endswith(".example.json"):
            return {
                "preset": preset_id,
                "configured": False,
                "available": False,
                "operations": [],
                "content_hash": digest,
                "path_label": _safe_path_label(path),
                "warnings": ["example preset only; copy to user_data/public_save_finish/krita_itsumono.json to enable"],
            }
        operations = data.get("operations")
        if not isinstance(operations, list):
            operations = []
        return {
            "preset": preset_id,
            "configured": True,
            "available": True,
            "operations": deepcopy(operations),
            "content_hash": digest,
            "path_label": _safe_path_label(path),
            "warnings": warnings,
        }
    return {
        "preset": preset_id,
        "configured": False,
        "available": False,
        "operations": [],
        "content_hash": "",
        "path_label": "",
        "warnings": ["krita_itsumono preset is not configured"],
    }


def public_save_finish_status(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    finish = public_save_finish_settings_from_app(settings)
    preset = load_public_save_finish_preset(finish["finish_preset"])
    operations = [op for op in preset.get("operations") or [] if isinstance(op, dict)]
    effective_operation_count = sum(1 for operation in operations if _operation_has_effect(operation))
    return {
        "enabled": bool(finish["finish_enabled"]),
        "preset": finish["finish_preset"],
        "configured": bool(preset.get("configured")),
        "available": bool(preset.get("available")),
        "path_label": preset.get("path_label", ""),
        "content_hash": preset.get("content_hash", ""),
        "operation_count": len(operations),
        "effective_operation_count": effective_operation_count,
        "warnings": preset.get("warnings") or [],
    }


def public_save_finish_hash_part(finish: dict[str, Any] | None) -> dict[str, Any]:
    settings = sanitize_public_save_finish_settings(finish)
    if not settings["finish_enabled"]:
        return {
            "finish_enabled": False,
            "finish_preset": settings["finish_preset"],
        }
    preset = load_public_save_finish_preset(settings["finish_preset"])
    return {
        "finish_enabled": settings["finish_enabled"],
        "finish_preset": settings["finish_preset"],
        "configured": bool(preset.get("configured")),
        "available": bool(preset.get("available")),
        "content_hash": preset.get("content_hash", ""),
    }


def public_save_finish_will_apply(finish: dict[str, Any] | None) -> bool:
    settings = sanitize_public_save_finish_settings(finish)
    if not settings["finish_enabled"]:
        return False
    preset = load_public_save_finish_preset(settings["finish_preset"])
    operations = [op for op in preset.get("operations") or [] if isinstance(op, dict)]
    return bool(preset.get("available") and operations)


def _apply_gamma(image: Image.Image, gamma: float) -> Image.Image:
    gamma = clamp_float(gamma, 1.0, 0.1, 5.0)
    if abs(gamma - 1.0) < 0.001:
        return image
    inv = 1.0 / gamma
    table = [min(255, max(0, int(((index / 255.0) ** inv) * 255 + 0.5))) for index in range(256)]
    return image.point(table * len(image.getbands()))


def _parse_curve_points(curve: Any) -> list[tuple[float, float, bool]]:
    if isinstance(curve, list):
        entries = curve
    else:
        entries = str(curve or "").split(";")
    raw_points: list[tuple[float, float, bool]] = []
    for entry in entries:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            raw_x, raw_y = entry[0], entry[1]
            flags = entry[2:]
        else:
            parts = [part.strip() for part in str(entry).split(",") if part.strip()]
            if len(parts) < 2:
                continue
            raw_x, raw_y = parts[0], parts[1]
            flags = parts[2:]
        try:
            x = float(raw_x)
            y = float(raw_y)
        except Exception:
            continue
        raw_points.append((x, y, any(str(flag).strip() == "is_corner" for flag in flags)))
    if not raw_points:
        return []
    max_coordinate = max(max(abs(point[0]), abs(point[1])) for point in raw_points)
    scale = 255.0 if max_coordinate > 1.0001 else 1.0
    points = [
        (
            clamp_float(point[0] / scale, 0.0, 0.0, 1.0),
            clamp_float(point[1] / scale, 0.0, 0.0, 1.0),
            point[2],
        )
        for point in raw_points
    ]
    deduped: dict[float, tuple[float, float, bool]] = {}
    for point in points:
        deduped[point[0]] = point
    return sorted(deduped.values(), key=lambda item: item[0])


def _natural_curve_table(curve: Any) -> list[int]:
    points = _parse_curve_points(curve)
    if len(points) < 2:
        points = [(0.0, 0.0, False), (1.0, 1.0, False)]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    if len(points) == 2:
        x0, x1 = xs[0], xs[1]
        y0, y1 = ys[0], ys[1]
        span = x1 - x0 or 1.0
        return [
            min(255, max(0, int((y0 + (y1 - y0) * ((min(max(index / 255.0, x0), x1) - x0) / span)) * 255 + 0.5)))
            for index in range(256)
        ]

    count = len(points)
    h = [max(0.000001, xs[index + 1] - xs[index]) for index in range(count - 1)]
    alpha = [0.0] * count
    for index in range(1, count - 1):
        alpha[index] = (
            (3.0 / h[index]) * (ys[index + 1] - ys[index])
            - (3.0 / h[index - 1]) * (ys[index] - ys[index - 1])
        )
    l = [1.0] + [0.0] * (count - 1)
    mu = [0.0] * count
    z = [0.0] * count
    for index in range(1, count - 1):
        l[index] = 2.0 * (xs[index + 1] - xs[index - 1]) - h[index - 1] * mu[index - 1]
        if abs(l[index]) < 0.000001:
            l[index] = 0.000001
        mu[index] = h[index] / l[index]
        z[index] = (alpha[index] - h[index - 1] * z[index - 1]) / l[index]
    l[-1] = 1.0
    c = [0.0] * count
    b = [0.0] * (count - 1)
    d = [0.0] * (count - 1)
    for index in range(count - 2, -1, -1):
        c[index] = z[index] - mu[index] * c[index + 1]
        b[index] = (ys[index + 1] - ys[index]) / h[index] - h[index] * (c[index + 1] + 2.0 * c[index]) / 3.0
        d[index] = (c[index + 1] - c[index]) / (3.0 * h[index])

    table: list[int] = []
    for index in range(256):
        x = min(max(index / 255.0, xs[0]), xs[-1])
        segment = max(0, min(len(b) - 1, bisect_right(xs, x) - 1))
        dx = x - xs[segment]
        y = ys[segment] + b[segment] * dx + c[segment] * dx * dx + d[segment] * dx * dx * dx
        table.append(min(255, max(0, int(min(max(y, 0.0), 1.0) * 255 + 0.5))))
    return table


def _is_identity_curve(curve: Any) -> bool:
    return _natural_curve_table(curve) == list(range(256))


def _operation_curves(operation: dict[str, Any]) -> dict[str, Any]:
    raw_curves = operation.get("curves") if isinstance(operation.get("curves"), dict) else {}
    curves = {str(key).strip().lower(): value for key, value in raw_curves.items()}
    for index in range(8):
        key = f"curve{index}"
        if key in operation and key not in curves:
            curves[key] = operation[key]
    return curves


def _apply_krita_perchannel(rgb: Image.Image, operation: dict[str, Any]) -> Image.Image:
    curves = _operation_curves(operation)
    all_colors = curves.get("curve0") or curves.get("all") or curves.get("all_colors") or curves.get("rgb")
    if all_colors and not _is_identity_curve(all_colors):
        rgb = rgb.point(_natural_curve_table(all_colors) * 3)
    channel_keys = [
        ("curve1", "red", "r"),
        ("curve2", "green", "g"),
        ("curve3", "blue", "b"),
    ]
    channels = list(rgb.split())
    changed = False
    for channel_index, keys in enumerate(channel_keys):
        curve = next((curves[key] for key in keys if key in curves), None)
        if curve and not _is_identity_curve(curve):
            channels[channel_index] = channels[channel_index].point(_natural_curve_table(curve))
            changed = True
    return Image.merge("RGB", channels) if changed else rgb


def _enhance(image: Image.Image, enhancer: type[ImageEnhance._Enhance], factor: Any, default: float = 1.0) -> Image.Image:
    factor = clamp_float(factor, default, 0.0, 4.0)
    if abs(factor - 1.0) < 0.001:
        return image
    return enhancer(image).enhance(factor)


def _apply_operation(rgb: Image.Image, operation: dict[str, Any]) -> Image.Image:
    op_type = str(operation.get("type") or "").strip().lower()
    if op_type in {"brightness", "brightness_contrast"}:
        if "brightness" in operation:
            brightness = clamp_float(operation.get("brightness"), 0.0, -1.0, 1.0)
            rgb = _enhance(rgb, ImageEnhance.Brightness, 1.0 + brightness)
        if "contrast" in operation:
            rgb = _enhance(rgb, ImageEnhance.Contrast, operation.get("contrast"))
        return rgb
    if op_type == "contrast":
        return _enhance(rgb, ImageEnhance.Contrast, operation.get("factor", operation.get("contrast")))
    if op_type in {"saturation", "color"}:
        return _enhance(rgb, ImageEnhance.Color, operation.get("factor", operation.get("saturation")))
    if op_type == "sharpness":
        return _enhance(rgb, ImageEnhance.Sharpness, operation.get("factor", operation.get("sharpness")))
    if op_type == "gamma":
        return _apply_gamma(rgb, operation.get("gamma", operation.get("factor", 1.0)))
    if op_type in {"krita_perchannel", "krita_perchannel_curves", "perchannel_curves"}:
        return _apply_krita_perchannel(rgb, operation)
    return rgb


def _operation_has_effect(operation: dict[str, Any]) -> bool:
    sample = Image.new("RGB", (256, 2))
    pixels: list[tuple[int, int, int]] = []
    for index in range(256):
        pixels.append((index, index, index))
    for index in range(256):
        pixels.append((index, 255 - index, (index * 53) % 256))
    sample.putdata(pixels)
    output = _apply_operation(sample, operation)
    return ImageChops.difference(sample, output).getbbox() is not None


def apply_public_save_finish(image: Image.Image, finish: dict[str, Any] | None) -> tuple[Image.Image, dict[str, Any]]:
    settings = sanitize_public_save_finish_settings(finish)
    preset = load_public_save_finish_preset(settings["finish_preset"])
    metadata = {
        "applied": False,
        "preset": settings["finish_preset"],
        "configured": bool(preset.get("configured")),
        "available": bool(preset.get("available")),
        "content_hash": preset.get("content_hash", ""),
        "operation_count": len([op for op in preset.get("operations") or [] if isinstance(op, dict)]),
        "effective_operation_count": 0,
        "changed_operation_count": 0,
        "warnings": list(preset.get("warnings") or []),
    }
    if not settings["finish_enabled"]:
        return image, metadata
    if not preset.get("available"):
        metadata["warnings"].append("finish preset missing; skipped")
        return image, metadata
    operations = [op for op in preset.get("operations") or [] if isinstance(op, dict)]
    if not operations:
        metadata["warnings"].append("finish preset has no operations; skipped")
        return image, metadata
    effective_operations = [operation for operation in operations if _operation_has_effect(operation)]
    metadata["effective_operation_count"] = len(effective_operations)
    if not effective_operations:
        metadata["warnings"].append("finish preset has no effective operations; skipped")
        return image, metadata
    working = image.convert("RGBA")
    alpha = working.getchannel("A")
    rgb = working.convert("RGB")
    changed_operation_count = 0
    for operation in effective_operations:
        before = rgb
        rgb = _apply_operation(rgb, operation)
        if ImageChops.difference(before, rgb).getbbox() is not None:
            changed_operation_count += 1
    metadata["changed_operation_count"] = changed_operation_count
    if ImageChops.difference(working.convert("RGB"), rgb).getbbox() is None:
        metadata["warnings"].append("finish preset did not change pixels; skipped")
        return image, metadata
    output = rgb.convert("RGBA")
    output.putalpha(alpha)
    metadata["applied"] = True
    return output, metadata
