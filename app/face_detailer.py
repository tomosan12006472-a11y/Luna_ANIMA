from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from ._shared_utils import next_node_id


DEFAULT_DETECTOR = "bbox/face_yolov8m.pt"
DEFAULT_SAM_MODEL = "sam_vit_b_01ec64.pth"


DEFAULT_FACE_DETAILER_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "mode": "generation",
    "detector": DEFAULT_DETECTOR,
    "steps": 12,
    "cfg": 5.0,
    "denoise": 0.3,
    "guide_size": 512,
    "max_size": 1024,
    "bbox_threshold": 0.5,
    "bbox_dilation": 10,
    "bbox_crop_factor": 3.0,
    "sam_enabled": False,
    "seed_policy": "image_seed_plus_offset",
    "seed_offset": 100000,
}


def _float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if not math.isfinite(number):
        number = default
    return max(minimum, min(maximum, number))


def _int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def sanitize_face_detailer_settings(value: Any, *, mode: str = "generation") -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    settings = deepcopy(DEFAULT_FACE_DETAILER_SETTINGS)
    settings.update(raw)
    settings["enabled"] = bool(settings.get("enabled"))
    settings["mode"] = "postprocess" if str(mode or settings.get("mode") or "") == "postprocess" else "generation"
    settings["detector"] = str(settings.get("detector") or DEFAULT_DETECTOR)
    settings["steps"] = _int(settings.get("steps"), 12, 1, 60)
    settings["cfg"] = _float(settings.get("cfg"), 5.0, 0.0, 30.0)
    settings["denoise"] = _float(settings.get("denoise"), 0.3, 0.0, 1.0)
    settings["guide_size"] = _int(settings.get("guide_size"), 512, 64, 2048)
    settings["max_size"] = _int(settings.get("max_size"), 1024, 128, 4096)
    settings["bbox_threshold"] = _float(settings.get("bbox_threshold"), 0.5, 0.0, 1.0)
    settings["bbox_dilation"] = _int(settings.get("bbox_dilation"), 10, -512, 512)
    settings["bbox_crop_factor"] = _float(settings.get("bbox_crop_factor"), 3.0, 1.0, 10.0)
    settings["sam_enabled"] = bool(settings.get("sam_enabled"))
    settings["seed_offset"] = _int(settings.get("seed_offset"), 100000, 0, 2147483647)
    if "seed" in settings and settings.get("seed") not in (None, ""):
        settings["seed"] = _int(settings.get("seed"), -1, -1, 4294967295)
    return settings


def face_detailer_seed(base_seed: Any, *, index: int = 0, settings: dict[str, Any] | None = None) -> int:
    settings = settings or {}
    explicit = settings.get("seed")
    if explicit not in (None, ""):
        seed = _int(explicit, -1, -1, 4294967295)
        if seed >= 0:
            return seed
    try:
        base = int(base_seed)
    except (TypeError, ValueError):
        base = 0
    if base < 0:
        base = 0
    offset = _int(settings.get("seed_offset"), 100000, 0, 2147483647)
    return (base + offset + int(index or 0)) % 4294967296


def _node_models(info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    node = info.get(class_name) if isinstance(info.get(class_name), dict) else {}
    inputs = node.get("input") if isinstance(node.get("input"), dict) else {}
    required = inputs.get("required") if isinstance(inputs.get("required"), dict) else {}
    value = required.get(input_name)
    if isinstance(value, list) and value and isinstance(value[0], list):
        return [str(item) for item in value[0]]
    return []


def face_detailer_capabilities(info: dict[str, Any] | None) -> dict[str, Any]:
    info = info or {}
    nodes = {
        "FaceDetailer": "FaceDetailer" in info,
        "UltralyticsDetectorProvider": "UltralyticsDetectorProvider" in info,
        "SAMLoader": "SAMLoader" in info,
    }
    detectors = _node_models(info, "UltralyticsDetectorProvider", "model_name")
    sams = _node_models(info, "SAMLoader", "model_name")
    warnings: list[str] = []
    if not nodes["FaceDetailer"]:
        warnings.append("FaceDetailer node is not available.")
    if not nodes["UltralyticsDetectorProvider"]:
        warnings.append("UltralyticsDetectorProvider node is not available.")
    if DEFAULT_DETECTOR not in detectors:
        warnings.append(f"Detector model is not available: {DEFAULT_DETECTOR}")
    return {
        "supported": nodes["FaceDetailer"] and nodes["UltralyticsDetectorProvider"] and DEFAULT_DETECTOR in detectors,
        "nodes": nodes,
        "models": {
            DEFAULT_DETECTOR: DEFAULT_DETECTOR in detectors,
            DEFAULT_SAM_MODEL: DEFAULT_SAM_MODEL in sams,
        },
        "detectors": detectors,
        "sam_models": sams,
        "postprocess_supported": nodes["FaceDetailer"] and nodes["UltralyticsDetectorProvider"] and DEFAULT_DETECTOR in detectors,
        "defaults": deepcopy(DEFAULT_FACE_DETAILER_SETTINGS),
        "warnings": warnings,
    }


def add_face_detailer_to_workflow(
    workflow: dict[str, Any],
    *,
    image: list[Any],
    model: list[Any],
    clip: list[Any],
    vae: list[Any],
    positive: list[Any],
    negative: list[Any],
    output_node_id: str,
    output_input_name: str,
    seed: int,
    settings: dict[str, Any],
) -> dict[str, Any]:
    settings = sanitize_face_detailer_settings(settings, mode=str(settings.get("mode") or "generation"))
    metadata = {
        "enabled": bool(settings.get("enabled")),
        "mode": settings.get("mode"),
        "detector": settings.get("detector"),
        "steps": settings.get("steps"),
        "cfg": settings.get("cfg"),
        "denoise": settings.get("denoise"),
        "guide_size": settings.get("guide_size"),
        "max_size": settings.get("max_size"),
        "bbox_threshold": settings.get("bbox_threshold"),
        "bbox_dilation": settings.get("bbox_dilation"),
        "bbox_crop_factor": settings.get("bbox_crop_factor"),
        "sam_enabled": bool(settings.get("sam_enabled")),
        "seed": seed,
        "warnings": [],
    }
    if not settings.get("enabled"):
        return metadata

    detector_id = next_node_id(workflow, 9300)
    workflow[detector_id] = {
        "class_type": "UltralyticsDetectorProvider",
        "inputs": {"model_name": settings.get("detector") or DEFAULT_DETECTOR},
        "_meta": {"title": "Face Detailer Detector"},
    }
    start = int(detector_id) + 1
    face_id = next_node_id(workflow, start)
    inputs: dict[str, Any] = {
        "image": image,
        "model": model,
        "clip": clip,
        "vae": vae,
        "guide_size": settings["guide_size"],
        "guide_size_for": True,
        "max_size": settings["max_size"],
        "seed": seed,
        "steps": settings["steps"],
        "cfg": settings["cfg"],
        "sampler_name": "euler",
        "scheduler": "normal",
        "positive": positive,
        "negative": negative,
        "denoise": settings["denoise"],
        "feather": 5,
        "noise_mask": True,
        "force_inpaint": True,
        "bbox_threshold": settings["bbox_threshold"],
        "bbox_dilation": settings["bbox_dilation"],
        "bbox_crop_factor": settings["bbox_crop_factor"],
        "sam_detection_hint": "center-1",
        "sam_dilation": 0,
        "sam_threshold": 0.93,
        "sam_bbox_expansion": 0,
        "sam_mask_hint_threshold": 0.7,
        "sam_mask_hint_use_negative": "False",
        "drop_size": 10,
        "bbox_detector": [detector_id, 0],
        "wildcard": "",
        "cycle": 1,
    }
    if settings.get("sam_enabled"):
        sam_id = next_node_id(workflow, int(face_id) + 1)
        workflow[sam_id] = {
            "class_type": "SAMLoader",
            "inputs": {"model_name": DEFAULT_SAM_MODEL, "device_mode": "AUTO"},
            "_meta": {"title": "Face Detailer SAM"},
        }
        inputs["sam_model_opt"] = [sam_id, 0]
        metadata["sam_node_id"] = sam_id
    workflow[face_id] = {
        "class_type": "FaceDetailer",
        "inputs": inputs,
        "_meta": {"title": "Face Detailer"},
    }
    workflow[str(output_node_id)]["inputs"][output_input_name] = [face_id, 0]
    metadata["node_id"] = face_id
    metadata["detector_node_id"] = detector_id
    metadata["applied"] = True
    return metadata
