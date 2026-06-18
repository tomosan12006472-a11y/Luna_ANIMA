from __future__ import annotations

from copy import deepcopy
from typing import Any

from .._shared_utils import next_node_id, sanitize_prompt_text
from ..anima_adapter import generate_seed
from ..face_detailer import (
    add_face_detailer_to_workflow,
    face_detailer_seed,
    sanitize_face_detailer_settings,
    sanitize_hand_detailer_settings,
)
from ..output_organizer import build_output_prefix
from .base import apply_model_sampling_shift, load_base_workflow
from .loras import apply_catalog_loras, apply_official_loras


def build_face_detailer_postprocess_workflow(request: dict[str, Any], image_name: str) -> dict[str, Any]:
    seed = generate_seed(request.get("seed"))
    positive = sanitize_prompt_text(request.get("positive_prompt") or request.get("positive") or "")
    negative = sanitize_prompt_text(request.get("negative_prompt") or request.get("negative") or "")
    model = str(request.get("model") or "Anima\\anima-preview3-base.safetensors")
    text_encoder = str(request.get("text_encoder") or "qwen_3_06b_base.safetensors")
    vae = str(request.get("vae") or "qwen_image_vae.safetensors")
    settings = sanitize_face_detailer_settings(request.get("face_detailer"), mode="postprocess")
    settings["enabled"] = True
    settings["mode"] = "postprocess"
    fd_seed = face_detailer_seed(seed, settings=settings)
    base = load_base_workflow()
    model_loader = deepcopy(base["44"])
    model_loader["inputs"]["model_name"] = model
    clip_loader = deepcopy(base["45"])
    clip_loader["inputs"]["clip_name"] = text_encoder
    vae_loader = deepcopy(base["15"])
    vae_loader["inputs"]["vae_name"] = vae
    workflow: dict[str, Any] = {
        "1": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": build_output_prefix(panel_id="anima", generation_method="face_detailer_postprocess", original_prefix="AnimaFaceDetailer"),
                "images": ["10", 0],
            },
            "_meta": {"title": "Save Face Detailer Result"},
        },
        "10": {"class_type": "LoadImage", "inputs": {"image": image_name}, "_meta": {"title": "Source Image"}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["45", 0]}, "_meta": {"title": "Positive"}},
        "12": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["45", 0]}, "_meta": {"title": "Negative"}},
        "15": vae_loader,
        "44": model_loader,
        "45": clip_loader,
        "46": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["44", 0], "shift": float(request.get("shift") or 4.0)}, "_meta": {"title": "Model Sampling"}},
    }
    apply_model_sampling_shift(workflow, request)
    previous_model = apply_official_loras(workflow, request)
    apply_catalog_loras(workflow, request, previous_model)
    metadata = add_face_detailer_to_workflow(
        workflow,
        image=["10", 0],
        model=["46", 0],
        clip=workflow["11"]["inputs"].get("clip", ["45", 0]),
        vae=["15", 0],
        positive=["11", 0],
        negative=["12", 0],
        output_node_id="1",
        output_input_name="images",
        seed=fd_seed,
        settings=settings,
    )
    request["face_detailer"] = metadata
    return workflow


def build_hand_detailer_postprocess_workflow(request: dict[str, Any], image_name: str) -> dict[str, Any]:
    seed = generate_seed(request.get("seed"))
    positive = sanitize_prompt_text(request.get("positive_prompt") or request.get("positive") or "")
    negative = sanitize_prompt_text(request.get("negative_prompt") or request.get("negative") or "")
    model = str(request.get("model") or "Anima\\anima-preview3-base.safetensors")
    text_encoder = str(request.get("text_encoder") or "qwen_3_06b_base.safetensors")
    vae = str(request.get("vae") or "qwen_image_vae.safetensors")
    settings = sanitize_hand_detailer_settings(request.get("hand_detailer"), mode="postprocess")
    settings["enabled"] = True
    settings["mode"] = "postprocess"
    hd_seed = face_detailer_seed(seed, settings=settings)
    base = load_base_workflow()
    model_loader = deepcopy(base["44"])
    model_loader["inputs"]["model_name"] = model
    clip_loader = deepcopy(base["45"])
    clip_loader["inputs"]["clip_name"] = text_encoder
    vae_loader = deepcopy(base["15"])
    vae_loader["inputs"]["vae_name"] = vae
    workflow: dict[str, Any] = {
        "1": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": build_output_prefix(panel_id="anima", generation_method="hand_detailer_postprocess", original_prefix="AnimaHandDetailer"),
                "images": ["10", 0],
            },
            "_meta": {"title": "Save Hand Detailer Result"},
        },
        "10": {"class_type": "LoadImage", "inputs": {"image": image_name}, "_meta": {"title": "Source Image"}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["45", 0]}, "_meta": {"title": "Positive"}},
        "12": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["45", 0]}, "_meta": {"title": "Negative"}},
        "15": vae_loader,
        "44": model_loader,
        "45": clip_loader,
        "46": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["44", 0], "shift": float(request.get("shift") or 4.0)}, "_meta": {"title": "Model Sampling"}},
    }
    apply_model_sampling_shift(workflow, request)
    previous_model = apply_official_loras(workflow, request)
    apply_catalog_loras(workflow, request, previous_model)
    lllite_model, lllite_metadata = add_hand_lllite_mask_to_workflow(
        workflow,
        image=["10", 0],
        model=["46", 0],
        settings=settings,
    )
    metadata = add_face_detailer_to_workflow(
        workflow,
        image=["10", 0],
        model=lllite_model,
        clip=workflow["11"]["inputs"].get("clip", ["45", 0]),
        vae=["15", 0],
        positive=["11", 0],
        negative=["12", 0],
        output_node_id="1",
        output_input_name="images",
        seed=hd_seed,
        settings=settings,
        title_prefix="Hand Detailer",
    )
    metadata["target"] = "hand"
    metadata["lllite"] = lllite_metadata
    request["hand_detailer"] = metadata
    return workflow


def apply_face_detailer(workflow: dict[str, Any], request: dict[str, Any], seed: int) -> None:
    settings = sanitize_face_detailer_settings(request.get("face_detailer"), mode="generation")
    settings["mode"] = "generation"
    fd_seed = face_detailer_seed(seed, index=int(request.get("queue_index") or 0), settings=settings)
    sampler_inputs = workflow["19"]["inputs"]
    metadata = add_face_detailer_to_workflow(
        workflow,
        image=workflow["1"]["inputs"].get("images") or ["8", 0],
        model=sampler_inputs.get("model"),
        clip=workflow["11"]["inputs"].get("clip", ["45", 0]),
        vae=["15", 0],
        positive=sampler_inputs.get("positive"),
        negative=sampler_inputs.get("negative"),
        output_node_id="1",
        output_input_name="images",
        seed=fd_seed,
        settings=settings,
    )
    request["face_detailer"] = metadata


def add_hand_lllite_mask_to_workflow(
    workflow: dict[str, Any],
    *,
    image: list[Any],
    model: list[Any],
    settings: dict[str, Any],
) -> tuple[list[Any], dict[str, Any]]:
    metadata = {
        "enabled": bool(settings.get("lllite_enabled")),
        "model": settings.get("lllite_model"),
        "strength": settings.get("lllite_strength"),
        "start_percent": settings.get("lllite_start"),
        "end_percent": settings.get("lllite_end"),
        "warnings": [],
    }
    if not settings.get("lllite_enabled"):
        metadata["applied"] = False
        return model, metadata

    detector_id = next_node_id(workflow, 9400)
    segs_id = next_node_id(workflow, int(detector_id) + 1)
    mask_id = next_node_id(workflow, int(segs_id) + 1)
    lllite_id = next_node_id(workflow, int(mask_id) + 1)
    workflow[detector_id] = {
        "class_type": "UltralyticsDetectorProvider",
        "inputs": {"model_name": settings.get("detector") or "bbox/hand_yolov8s.pt"},
        "_meta": {"title": "Hand LLLite Detector"},
    }
    workflow[segs_id] = {
        "class_type": "BboxDetectorSEGS",
        "inputs": {
            "bbox_detector": [detector_id, 0],
            "image": image,
            "threshold": settings["bbox_threshold"],
            "dilation": settings["bbox_dilation"],
            "crop_factor": settings["bbox_crop_factor"],
            "drop_size": settings["drop_size"],
            "labels": "hand",
        },
        "_meta": {"title": "Hand LLLite SEGS"},
    }
    workflow[mask_id] = {
        "class_type": "SegsToCombinedMask",
        "inputs": {"segs": [segs_id, 0]},
        "_meta": {"title": "Hand LLLite Mask"},
    }
    workflow[lllite_id] = {
        "class_type": "AnimaLLLiteApply",
        "inputs": {
            "model": model,
            "lllite_name": settings["lllite_model"],
            "image": image,
            "strength": settings["lllite_strength"],
            "start_percent": settings["lllite_start"],
            "end_percent": settings["lllite_end"],
            "preserve_wrapper": True,
            "mask": [mask_id, 0],
        },
        "_meta": {"title": "Hand LLLite Inpainting"},
    }
    metadata.update(
        {
            "applied": True,
            "detector_node_id": detector_id,
            "segs_node_id": segs_id,
            "mask_node_id": mask_id,
            "node_id": lllite_id,
        }
    )
    return [lllite_id, 0], metadata


def apply_hand_detailer(workflow: dict[str, Any], request: dict[str, Any], seed: int) -> None:
    settings = sanitize_hand_detailer_settings(request.get("hand_detailer"), mode="generation")
    settings["mode"] = "generation"
    hd_seed = face_detailer_seed(seed, index=int(request.get("queue_index") or 0), settings=settings)
    if not settings.get("enabled"):
        request["hand_detailer"] = {
            "enabled": False,
            "mode": "generation",
            "detector": settings.get("detector"),
            "lllite": {"enabled": bool(settings.get("lllite_enabled")), "applied": False},
        }
        return
    image = workflow["1"]["inputs"].get("images") or ["8", 0]
    sampler_inputs = workflow["19"]["inputs"]
    model = sampler_inputs.get("model")
    lllite_model, lllite_metadata = add_hand_lllite_mask_to_workflow(
        workflow,
        image=image,
        model=model,
        settings=settings,
    )
    metadata = add_face_detailer_to_workflow(
        workflow,
        image=image,
        model=lllite_model,
        clip=workflow["11"]["inputs"].get("clip", ["45", 0]),
        vae=["15", 0],
        positive=sampler_inputs.get("positive"),
        negative=sampler_inputs.get("negative"),
        output_node_id="1",
        output_input_name="images",
        seed=hd_seed,
        settings=settings,
        title_prefix="Hand Detailer",
    )
    metadata["target"] = "hand"
    metadata["lllite"] = lllite_metadata
    request["hand_detailer"] = metadata

def build_face_detailer_postprocess_payload(request: dict[str, Any], client_id: str, image_name: str) -> dict[str, Any]:
    return {"prompt": build_face_detailer_postprocess_workflow(request, image_name), "client_id": client_id}


def build_hand_detailer_postprocess_payload(request: dict[str, Any], client_id: str, image_name: str) -> dict[str, Any]:
    return {"prompt": build_hand_detailer_postprocess_workflow(request, image_name), "client_id": client_id}
