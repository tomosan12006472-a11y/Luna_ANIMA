from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from ._shared_utils import next_node_id
from .schemas.generation import FaceDetailerRequestSettings, HandDetailerRequestSettings


DEFAULT_DETECTOR = "bbox/face_yolov8m.pt"
DEFAULT_HAND_DETECTOR = "bbox/hand_yolov8s.pt"
DEFAULT_SAM_MODEL = "sam_vit_b_01ec64.pth"
DEFAULT_ANIMA_LLLITE_INPAINTING = "anima-lllite-inpainting-v2.safetensors"
DEFAULT_DETAILER_SAMPLER = "euler"
DEFAULT_DETAILER_SCHEDULER = "normal"


DEFAULT_FACE_DETAILER_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "mode": "generation",
    "preset": "normal",
    "detector": DEFAULT_DETECTOR,
    "steps": 12,
    "cfg": 5.0,
    "denoise": 0.3,
    "sampler_mode": "custom",
    "sampler": DEFAULT_DETAILER_SAMPLER,
    "scheduler": DEFAULT_DETAILER_SCHEDULER,
    "guide_size": 512,
    "max_size": 1024,
    "bbox_threshold": 0.65,
    "bbox_dilation": 10,
    "bbox_crop_factor": 3.0,
    "drop_size": 64,
    "min_area_ratio": 0.0008,
    "max_area_ratio": 1.0,
    "max_detections": 8,
    "runaway_guard_enabled": True,
    "runaway_max_candidates": 20,
    "runaway_action": "skip",
    "sam_enabled": False,
    "seed_policy": "image_seed_plus_offset",
    "seed_offset": 100000,
}


DEFAULT_HAND_DETAILER_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "mode": "generation",
    "preset": "normal",
    "detector": DEFAULT_HAND_DETECTOR,
    "steps": 14,
    "cfg": 4.0,
    "denoise": 0.45,
    "sampler_mode": "custom",
    "sampler": DEFAULT_DETAILER_SAMPLER,
    "scheduler": DEFAULT_DETAILER_SCHEDULER,
    "guide_size": 512,
    "max_size": 1024,
    "bbox_threshold": 0.45,
    "bbox_dilation": 16,
    "bbox_crop_factor": 2.5,
    "drop_size": 24,
    "min_area_ratio": 0.0005,
    "max_area_ratio": 0.35,
    "max_detections": 12,
    "runaway_guard_enabled": True,
    "runaway_max_candidates": 30,
    "runaway_action": "skip",
    "sam_enabled": False,
    "seed_policy": "image_seed_plus_offset",
    "seed_offset": 200000,
    "lllite_enabled": True,
    "lllite_model": DEFAULT_ANIMA_LLLITE_INPAINTING,
    "lllite_strength": 0.85,
    "lllite_start": 0.0,
    "lllite_end": 1.0,
}


DETAILER_DETECTION_PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    "face": {
        "safe": {
            "bbox_threshold": 0.75,
            "min_area_ratio": 0.0010,
            "max_area_ratio": 1.0,
            "max_detections": 4,
            "runaway_guard_enabled": True,
            "runaway_max_candidates": 12,
            "runaway_action": "skip",
        },
        "normal": {
            "bbox_threshold": 0.65,
            "min_area_ratio": 0.0008,
            "max_area_ratio": 1.0,
            "max_detections": 8,
            "runaway_guard_enabled": True,
            "runaway_max_candidates": 20,
            "runaway_action": "skip",
        },
        "aggressive": {
            "bbox_threshold": 0.50,
            "min_area_ratio": 0.0004,
            "max_area_ratio": 1.0,
            "max_detections": 16,
            "runaway_guard_enabled": True,
            "runaway_max_candidates": 40,
            "runaway_action": "limit",
        },
    },
    "hand": {
        "safe": {
            "bbox_threshold": 0.55,
            "min_area_ratio": 0.0008,
            "max_area_ratio": 0.35,
            "max_detections": 6,
            "runaway_guard_enabled": True,
            "runaway_max_candidates": 16,
            "runaway_action": "skip",
        },
        "normal": {
            "bbox_threshold": 0.45,
            "min_area_ratio": 0.0005,
            "max_area_ratio": 0.35,
            "max_detections": 12,
            "runaway_guard_enabled": True,
            "runaway_max_candidates": 30,
            "runaway_action": "skip",
        },
        "aggressive": {
            "bbox_threshold": 0.35,
            "min_area_ratio": 0.0003,
            "max_area_ratio": 0.45,
            "max_detections": 20,
            "runaway_guard_enabled": True,
            "runaway_max_candidates": 50,
            "runaway_action": "limit",
        },
    },
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


def _detailer_sampling_value(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def resolve_detailer_sampling(
    settings: dict[str, Any],
    *,
    source_sampler: Any = None,
    source_scheduler: Any = None,
) -> tuple[str, str]:
    if str(settings.get("sampler_mode") or "custom") == "source":
        sampler = _detailer_sampling_value(source_sampler, settings.get("sampler") or DEFAULT_DETAILER_SAMPLER)
        scheduler = _detailer_sampling_value(source_scheduler, settings.get("scheduler") or DEFAULT_DETAILER_SCHEDULER)
        return sampler, scheduler
    return (
        _detailer_sampling_value(settings.get("sampler"), DEFAULT_DETAILER_SAMPLER),
        _detailer_sampling_value(settings.get("scheduler"), DEFAULT_DETAILER_SCHEDULER),
    )


def detailer_preset_settings(kind: str, preset: str) -> dict[str, Any]:
    return deepcopy(DETAILER_DETECTION_PRESETS.get(kind, {}).get(preset, {}))


def _area_pixels(width: Any, height: Any, ratio: Any, default_width: int = 1024, default_height: int = 1536) -> int:
    w = _int(width, default_width, 64, 16384)
    h = _int(height, default_height, 64, 16384)
    value = _float(ratio, 0.0, 0.0, 1.0)
    return max(0, int(math.ceil(w * h * value)))


def sanitize_face_detailer_settings(value: Any, *, mode: str = "generation") -> dict[str, Any]:
    raw = value.model_dump() if hasattr(value, "model_dump") else value if isinstance(value, dict) else {}
    settings = FaceDetailerRequestSettings.model_validate({**raw, "mode": mode}).model_dump()
    if "seed" in raw and raw.get("seed") not in (None, ""):
        settings["seed"] = _int(raw.get("seed"), -1, -1, 4294967295)
    return settings


def sanitize_hand_detailer_settings(value: Any, *, mode: str = "generation") -> dict[str, Any]:
    raw = value.model_dump() if hasattr(value, "model_dump") else value if isinstance(value, dict) else {}
    settings = HandDetailerRequestSettings.model_validate({**raw, "mode": mode}).model_dump()
    if "seed" in raw and raw.get("seed") not in (None, ""):
        settings["seed"] = _int(raw.get("seed"), -1, -1, 4294967295)
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
        "DetailerForEach": "DetailerForEach" in info,
        "UltralyticsDetectorProvider": "UltralyticsDetectorProvider" in info,
        "SAMLoader": "SAMLoader" in info,
        "BboxDetectorSEGS": "BboxDetectorSEGS" in info,
        "ImpactSEGSRangeFilter": "ImpactSEGSRangeFilter" in info,
        "ImpactSEGSOrderedFilter": "ImpactSEGSOrderedFilter" in info,
        "ImpactCount_Elts_in_SEGS": "ImpactCount_Elts_in_SEGS" in info,
        "ImpactCompare": "ImpactCompare" in info,
        "ImpactInt": "ImpactInt" in info,
        "ImpactConditionalBranch": "ImpactConditionalBranch" in info,
        "EmptySegs": "EmptySegs" in info,
        "SegsToCombinedMask": "SegsToCombinedMask" in info,
        "AnimaLLLiteApply": "AnimaLLLiteApply" in info,
    }
    detectors = _node_models(info, "UltralyticsDetectorProvider", "model_name")
    sams = _node_models(info, "SAMLoader", "model_name")
    lllite_models = _node_models(info, "AnimaLLLiteApply", "lllite_name")
    warnings: list[str] = []
    if not nodes["FaceDetailer"]:
        warnings.append("FaceDetailer node is not available.")
    if not nodes["DetailerForEach"]:
        warnings.append("DetailerForEach node is not available; detection controls require DetailerForEach.")
    for node_name in (
        "BboxDetectorSEGS",
        "ImpactSEGSRangeFilter",
        "ImpactSEGSOrderedFilter",
        "ImpactCount_Elts_in_SEGS",
        "ImpactInt",
        "ImpactCompare",
        "ImpactConditionalBranch",
        "EmptySegs",
    ):
        if not nodes[node_name]:
            warnings.append(f"{node_name} node is not available; detection controls may not run.")
    if not nodes["UltralyticsDetectorProvider"]:
        warnings.append("UltralyticsDetectorProvider node is not available.")
    if DEFAULT_DETECTOR not in detectors:
        warnings.append(f"Detector model is not available: {DEFAULT_DETECTOR}")
    hand_warnings: list[str] = []
    for node_name in (
        "FaceDetailer",
        "DetailerForEach",
        "UltralyticsDetectorProvider",
        "BboxDetectorSEGS",
        "ImpactSEGSRangeFilter",
        "ImpactSEGSOrderedFilter",
        "ImpactCount_Elts_in_SEGS",
        "ImpactInt",
        "ImpactCompare",
        "ImpactConditionalBranch",
        "EmptySegs",
        "SegsToCombinedMask",
        "AnimaLLLiteApply",
    ):
        if not nodes[node_name]:
            hand_warnings.append(f"{node_name} node is not available.")
    if DEFAULT_HAND_DETECTOR not in detectors:
        hand_warnings.append(f"Detector model is not available: {DEFAULT_HAND_DETECTOR}")
    if DEFAULT_ANIMA_LLLITE_INPAINTING not in lllite_models:
        hand_warnings.append(f"Anima LLLite model is not available: {DEFAULT_ANIMA_LLLITE_INPAINTING}")
    hand_supported = (
        nodes["FaceDetailer"]
        and nodes["DetailerForEach"]
        and nodes["UltralyticsDetectorProvider"]
        and nodes["BboxDetectorSEGS"]
        and nodes["ImpactSEGSRangeFilter"]
        and nodes["ImpactSEGSOrderedFilter"]
        and nodes["ImpactCount_Elts_in_SEGS"]
        and nodes["ImpactInt"]
        and nodes["ImpactCompare"]
        and nodes["ImpactConditionalBranch"]
        and nodes["EmptySegs"]
        and nodes["SegsToCombinedMask"]
        and nodes["AnimaLLLiteApply"]
        and DEFAULT_HAND_DETECTOR in detectors
        and DEFAULT_ANIMA_LLLITE_INPAINTING in lllite_models
    )
    supported = (
        nodes["FaceDetailer"]
        and nodes["DetailerForEach"]
        and nodes["UltralyticsDetectorProvider"]
        and nodes["BboxDetectorSEGS"]
        and nodes["ImpactSEGSRangeFilter"]
        and nodes["ImpactSEGSOrderedFilter"]
        and nodes["ImpactCount_Elts_in_SEGS"]
        and nodes["ImpactInt"]
        and nodes["ImpactCompare"]
        and nodes["ImpactConditionalBranch"]
        and nodes["EmptySegs"]
        and DEFAULT_DETECTOR in detectors
    )
    return {
        "supported": supported,
        "nodes": nodes,
        "models": {
            DEFAULT_DETECTOR: DEFAULT_DETECTOR in detectors,
            DEFAULT_HAND_DETECTOR: DEFAULT_HAND_DETECTOR in detectors,
            DEFAULT_SAM_MODEL: DEFAULT_SAM_MODEL in sams,
            DEFAULT_ANIMA_LLLITE_INPAINTING: DEFAULT_ANIMA_LLLITE_INPAINTING in lllite_models,
        },
        "detectors": detectors,
        "sam_models": sams,
        "lllite_models": lllite_models,
        "postprocess_supported": supported,
        "defaults": deepcopy(DEFAULT_FACE_DETAILER_SETTINGS),
        "detection_presets": deepcopy(DETAILER_DETECTION_PRESETS),
        "hand_supported": hand_supported,
        "hand_detailer": {
            "supported": hand_supported,
            "defaults": deepcopy(DEFAULT_HAND_DETAILER_SETTINGS),
            "detection_presets": deepcopy(DETAILER_DETECTION_PRESETS["hand"]),
            "detector": DEFAULT_HAND_DETECTOR,
            "lllite_model": DEFAULT_ANIMA_LLLITE_INPAINTING,
            "warnings": hand_warnings,
        },
        "warnings": warnings,
    }


def _detailer_metadata(settings: dict[str, Any], *, seed: int, target: str) -> dict[str, Any]:
    return {
        "detailer_type": target,
        "enabled": bool(settings.get("enabled")),
        "mode": settings.get("mode"),
        "preset": settings.get("preset"),
        "detector": settings.get("detector"),
        "detector_model": settings.get("detector"),
        "steps": settings.get("steps"),
        "cfg": settings.get("cfg"),
        "denoise": settings.get("denoise"),
        "sampler_mode": settings.get("sampler_mode"),
        "sampler": settings.get("sampler"),
        "scheduler": settings.get("scheduler"),
        "guide_size": settings.get("guide_size"),
        "max_size": settings.get("max_size"),
        "bbox_threshold": settings.get("bbox_threshold"),
        "bbox_dilation": settings.get("bbox_dilation"),
        "bbox_crop_factor": settings.get("bbox_crop_factor"),
        "drop_size": settings.get("drop_size"),
        "min_area_ratio": settings.get("min_area_ratio"),
        "max_area_ratio": settings.get("max_area_ratio"),
        "max_detections": settings.get("max_detections"),
        "runaway_guard_enabled": bool(settings.get("runaway_guard_enabled")),
        "runaway_max_candidates": settings.get("runaway_max_candidates"),
        "runaway_action": settings.get("runaway_action"),
        "runaway_guard_note": "",
        "candidates_detected": None,
        "candidates_processed": None,
        "max_candidates_processed": settings.get("max_detections"),
        "elapsed_seconds": None,
        "skipped": False,
        "skip_reason": "",
        "sam_enabled": bool(settings.get("sam_enabled")),
        "seed": seed,
        "warnings": [],
    }


def add_detection_segs_to_workflow(
    workflow: dict[str, Any],
    *,
    image: list[Any],
    detector: list[Any],
    settings: dict[str, Any],
    title_prefix: str,
    label: str,
    image_width: Any = None,
    image_height: Any = None,
    start: int = 9300,
) -> tuple[list[Any], dict[str, Any]]:
    segs_id = next_node_id(workflow, start)
    workflow[segs_id] = {
        "class_type": "BboxDetectorSEGS",
        "inputs": {
            "bbox_detector": detector,
            "image": image,
            "threshold": settings["bbox_threshold"],
            "dilation": settings["bbox_dilation"],
            "crop_factor": settings["bbox_crop_factor"],
            "drop_size": settings["drop_size"],
            "labels": label,
        },
        "_meta": {"title": f"{title_prefix} Candidates"},
    }
    min_area = _area_pixels(image_width, image_height, settings.get("min_area_ratio"))
    max_area = _area_pixels(image_width, image_height, settings.get("max_area_ratio"), default_width=1024, default_height=1536)
    max_area = max(min_area, max_area)
    area_id = next_node_id(workflow, int(segs_id) + 1)
    workflow[area_id] = {
        "class_type": "ImpactSEGSRangeFilter",
        "inputs": {
            "segs": [segs_id, 0],
            "target": "area(=w*h)",
            "mode": True,
            "min_value": min_area,
            "max_value": max_area,
        },
        "_meta": {"title": f"{title_prefix} Area Filter"},
    }
    limit_id = next_node_id(workflow, int(area_id) + 1)
    workflow[limit_id] = {
        "class_type": "ImpactSEGSOrderedFilter",
        "inputs": {
            "segs": [area_id, 0],
            "target": "confidence",
            "order": True,
            "take_start": 0,
            "take_count": settings["max_detections"],
        },
        "_meta": {"title": f"{title_prefix} Max Detections"},
    }
    metadata: dict[str, Any] = {
        "segs_node_id": segs_id,
        "area_filter_node_id": area_id,
        "max_filter_node_id": limit_id,
        "candidate_count_node_id": None,
        "min_area_pixels": min_area,
        "max_area_pixels": max_area,
        "max_detections_supported": True,
        "runaway_guard_supported": False,
        "runaway_guard_node_id": None,
    }
    final_segs: list[Any] = [limit_id, 0]
    action = str(settings.get("runaway_action") or "skip")
    if settings.get("runaway_guard_enabled"):
        count_id = next_node_id(workflow, int(limit_id) + 1)
        threshold_id = next_node_id(workflow, int(count_id) + 1)
        compare_id = next_node_id(workflow, int(threshold_id) + 1)
        workflow[count_id] = {
            "class_type": "ImpactCount_Elts_in_SEGS",
            "inputs": {"segs": [area_id, 0]},
            "_meta": {"title": f"{title_prefix} Candidate Count"},
        }
        workflow[threshold_id] = {
            "class_type": "ImpactInt",
            "inputs": {"value": settings["runaway_max_candidates"]},
            "_meta": {"title": f"{title_prefix} Runaway Threshold"},
        }
        workflow[compare_id] = {
            "class_type": "ImpactCompare",
            "inputs": {"cmp": "a > b", "a": [count_id, 0], "b": [threshold_id, 0]},
            "_meta": {"title": f"{title_prefix} Runaway Compare"},
        }
        metadata.update(
            {
                "candidate_count_node_id": count_id,
                "runaway_compare_node_id": compare_id,
                "runaway_guard_supported": True,
            }
        )
        if action == "skip":
            empty_id = next_node_id(workflow, int(compare_id) + 1)
            branch_id = next_node_id(workflow, int(empty_id) + 1)
            workflow[empty_id] = {
                "class_type": "EmptySegs",
                "inputs": {},
                "_meta": {"title": f"{title_prefix} Empty SEGS"},
            }
            workflow[branch_id] = {
                "class_type": "ImpactConditionalBranch",
                "inputs": {"cond": [compare_id, 0], "tt_value": [empty_id, 0], "ff_value": [limit_id, 0]},
                "_meta": {"title": f"{title_prefix} Runaway Guard"},
            }
            final_segs = [branch_id, 0]
            metadata.update(
                {
                    "empty_segs_node_id": empty_id,
                    "runaway_guard_node_id": branch_id,
                    "runaway_guard_note": f"candidate count > {settings['runaway_max_candidates']} routes an empty SEGS set at runtime",
                }
            )
        elif action == "limit":
            metadata["runaway_guard_note"] = f"candidate count > {settings['runaway_max_candidates']} is limited to {settings['max_detections']} detections at runtime"
        elif action == "warn":
            metadata["runaway_guard_note"] = f"candidate count > {settings['runaway_max_candidates']} records a warning at runtime; max detections still limits processing"
    return final_segs, metadata


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
    title_prefix: str = "Face Detailer",
    target: str = "face",
    image_width: Any = None,
    image_height: Any = None,
    source_sampler: Any = None,
    source_scheduler: Any = None,
) -> dict[str, Any]:
    mode = str(settings.get("mode") or "generation")
    if target == "hand":
        settings = sanitize_hand_detailer_settings(settings, mode=mode)
    else:
        settings = sanitize_face_detailer_settings(settings, mode=mode)
    sampler_name, scheduler = resolve_detailer_sampling(settings, source_sampler=source_sampler, source_scheduler=source_scheduler)
    settings["sampler"] = sampler_name
    settings["scheduler"] = scheduler
    metadata = _detailer_metadata(settings, seed=seed, target=target)
    if not settings.get("enabled"):
        return metadata

    detector_id = next_node_id(workflow, 9300)
    workflow[detector_id] = {
        "class_type": "UltralyticsDetectorProvider",
        "inputs": {"model_name": settings.get("detector") or DEFAULT_DETECTOR},
        "_meta": {"title": f"{title_prefix} Detector"},
    }
    start = int(detector_id) + 1
    detailer_id = next_node_id(workflow, start)

    if not settings.get("sam_enabled"):
        label = "hand" if target == "hand" else "all"
        segs, segs_metadata = add_detection_segs_to_workflow(
            workflow,
            image=image,
            detector=[detector_id, 0],
            settings=settings,
            title_prefix=title_prefix,
            label=label,
            image_width=image_width,
            image_height=image_height,
        )
        detailer_id = next_node_id(workflow, int(segs_metadata["runaway_guard_node_id"] or segs_metadata["max_filter_node_id"]) + 1)
        workflow[detailer_id] = {
            "class_type": "DetailerForEach",
            "inputs": {
                "image": image,
                "segs": segs,
                "model": model,
                "clip": clip,
                "vae": vae,
                "guide_size": settings["guide_size"],
                "guide_size_for": True,
                "max_size": settings["max_size"],
                "seed": seed,
                "steps": settings["steps"],
                "cfg": settings["cfg"],
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "positive": positive,
                "negative": negative,
                "denoise": settings["denoise"],
                "feather": 5,
                "noise_mask": True,
                "force_inpaint": True,
                "wildcard": "",
                "cycle": 1,
            },
            "_meta": {"title": title_prefix},
        }
        workflow[str(output_node_id)]["inputs"][output_input_name] = [detailer_id, 0]
        metadata.update(segs_metadata)
        metadata["node_id"] = detailer_id
        metadata["detector_node_id"] = detector_id
        metadata["node_type"] = "DetailerForEach"
        metadata["applied"] = True
        return metadata

    metadata["warnings"].append("sam_enabled uses FaceDetailer compatibility mode; max_detections and runaway guard are not enforced by node inputs.")
    face_id = detailer_id
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
        "sampler_name": sampler_name,
        "scheduler": scheduler,
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
        "drop_size": settings.get("drop_size", 64),
        "bbox_detector": [detector_id, 0],
        "wildcard": "",
        "cycle": 1,
    }
    if settings.get("sam_enabled"):
        sam_id = next_node_id(workflow, int(face_id) + 1)
        workflow[sam_id] = {
            "class_type": "SAMLoader",
            "inputs": {"model_name": DEFAULT_SAM_MODEL, "device_mode": "AUTO"},
            "_meta": {"title": f"{title_prefix} SAM"},
        }
        inputs["sam_model_opt"] = [sam_id, 0]
        metadata["sam_node_id"] = sam_id
    workflow[face_id] = {
        "class_type": "FaceDetailer",
        "inputs": inputs,
        "_meta": {"title": title_prefix},
    }
    workflow[str(output_node_id)]["inputs"][output_input_name] = [face_id, 0]
    metadata["node_id"] = face_id
    metadata["detector_node_id"] = detector_id
    metadata["node_type"] = "FaceDetailer"
    metadata["max_detections_supported"] = False
    metadata["runaway_guard_supported"] = False
    metadata["applied"] = True
    return metadata
