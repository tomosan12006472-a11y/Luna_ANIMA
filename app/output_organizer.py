from __future__ import annotations

from datetime import datetime
import re
from typing import Any


_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _sanitize_segment(value: Any, fallback: str) -> str:
    text = str(value or "").replace("\\", "/").strip()
    parts = [part for part in text.split("/") if part and part not in {".", ".."}]
    text = "_".join(parts) if parts else fallback
    text = _SAFE_SEGMENT_RE.sub("_", text).strip("._-")
    return text or fallback


def output_date(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d")


def build_output_subfolder(
    *,
    panel_id: str,
    generation_method: str,
    now: datetime | None = None,
) -> str:
    return "/".join(
        [
            output_date(now),
            _sanitize_segment(panel_id, "panel"),
            _sanitize_segment(generation_method, "standard"),
        ]
    )


def build_output_prefix(
    *,
    panel_id: str,
    generation_method: str,
    original_prefix: str,
    now: datetime | None = None,
) -> str:
    return "/".join(
        [
            build_output_subfolder(panel_id=panel_id, generation_method=generation_method, now=now),
            _sanitize_segment(original_prefix, "output"),
        ]
    )


def infer_anima_generation_method(request: dict[str, Any]) -> str:
    operation = str(request.get("operation") or "")
    if operation == "face_detailer_postprocess":
        return "face_detailer_postprocess"
    if operation == "hand_detailer_postprocess":
        return "hand_detailer_postprocess"
    ref = request.get("reference_assist") if isinstance(request.get("reference_assist"), dict) else {}
    modules = request.get("reference_modules") if isinstance(request.get("reference_modules"), dict) else {}
    i2i = request.get("image_to_image") if isinstance(request.get("image_to_image"), dict) else {}
    hires = request.get("hires_fix") if isinstance(request.get("hires_fix"), dict) else {}
    official = request.get("official_loras") if isinstance(request.get("official_loras"), dict) else {}
    face_detailer = request.get("face_detailer") if isinstance(request.get("face_detailer"), dict) else {}
    hand_detailer = request.get("hand_detailer") if isinstance(request.get("hand_detailer"), dict) else {}
    turbo = official.get("turbo") if isinstance(official.get("turbo"), dict) else {}
    reference_enabled = bool(ref.get("apply_to_payload"))
    outfit_enabled = bool((modules.get("outfit") or {}).get("apply_to_payload"))
    pose_enabled = bool((modules.get("pose") or {}).get("apply_to_payload"))
    i2i_enabled = bool(i2i.get("apply_to_payload"))
    turbo_enabled = bool(turbo.get("enabled"))
    hires_enabled = bool(hires.get("enabled"))
    face_enabled = bool(face_detailer.get("enabled"))
    hand_enabled = bool(hand_detailer.get("enabled"))
    hires_mode = str(hires.get("mode") or "latent").lower()
    hires_suffix = "hires_model" if hires_mode == "model" else "hires_latent"
    if face_enabled and hand_enabled and i2i_enabled:
        return "face_hand_detailer_i2i"
    if face_enabled and hand_enabled and reference_enabled and hires_enabled:
        return f"face_hand_detailer_reference_{hires_suffix}"
    if face_enabled and hand_enabled and turbo_enabled and hires_enabled:
        return f"face_hand_detailer_turbo_{hires_suffix}"
    if face_enabled and hand_enabled and reference_enabled:
        return "face_hand_detailer_reference"
    if face_enabled and hand_enabled and turbo_enabled:
        return "face_hand_detailer_turbo"
    if face_enabled and hand_enabled and hires_enabled:
        return f"face_hand_detailer_{hires_suffix}"
    if face_enabled and hand_enabled:
        return "face_hand_detailer"
    if hand_enabled and i2i_enabled:
        return "hand_detailer_i2i"
    if hand_enabled and reference_enabled and hires_enabled:
        return f"hand_detailer_reference_{hires_suffix}"
    if hand_enabled and turbo_enabled and hires_enabled:
        return f"hand_detailer_turbo_{hires_suffix}"
    if hand_enabled and reference_enabled:
        return "hand_detailer_reference"
    if hand_enabled and turbo_enabled:
        return "hand_detailer_turbo"
    if hand_enabled and hires_enabled:
        return f"hand_detailer_{hires_suffix}"
    if hand_enabled:
        return "hand_detailer"
    if face_enabled and i2i_enabled:
        return "face_detailer_i2i"
    if face_enabled and reference_enabled and hires_enabled:
        return f"face_detailer_reference_{hires_suffix}"
    if face_enabled and turbo_enabled and hires_enabled:
        return f"face_detailer_turbo_{hires_suffix}"
    if face_enabled and reference_enabled:
        return "face_detailer_reference"
    if face_enabled and turbo_enabled:
        return "face_detailer_turbo"
    if face_enabled and hires_enabled:
        return f"face_detailer_{hires_suffix}"
    if face_enabled:
        return "face_detailer"
    if reference_enabled and hires_enabled:
        return f"reference_{hires_suffix}"
    if turbo_enabled and hires_enabled:
        return f"turbo_{hires_suffix}"
    if reference_enabled:
        return "reference"
    if outfit_enabled and pose_enabled:
        return "reference_outfit_pose"
    if pose_enabled:
        return "reference_pose"
    if outfit_enabled:
        return "reference_outfit"
    if turbo_enabled:
        return "turbo"
    if i2i_enabled:
        return "i2i"
    if hires_enabled:
        return hires_suffix
    return "standard"


def organization_metadata(
    *,
    panel_id: str,
    generation_method: str,
    original_prefix: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "date": output_date(now),
        "panel": _sanitize_segment(panel_id, "panel"),
        "method": _sanitize_segment(generation_method, "standard"),
        "filename_prefix": build_output_prefix(
            panel_id=panel_id,
            generation_method=generation_method,
            original_prefix=original_prefix,
            now=now,
        ),
    }
