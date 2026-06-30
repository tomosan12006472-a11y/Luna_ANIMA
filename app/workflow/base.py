from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Any

from ..config import ANIMA_MAPPING_PATH, ANIMA_WORKFLOW_PATH
from ..output_organizer import build_output_prefix, infer_anima_generation_method
from .hires import apply_hires_fix
from .i2i import apply_image_to_image
from .loras import apply_catalog_loras, apply_official_loras
from .prompts import LORA_SAMPLE_MODEL_NAME, build_prompts, is_lora_sample_mode
from .reference import apply_reference_assist, apply_reference_modules


_JSON_CACHE: dict[Path, tuple[tuple[int, int], dict[str, Any]]] = {}


def _load_json_dict_cached(path: Path, *, strict: bool) -> dict[str, Any]:
    signature: tuple[int, int] | None = None
    try:
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = _JSON_CACHE.get(path)
        if cached and cached[0] == signature:
            return deepcopy(cached[1])
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        if strict:
            raise
        return {}
    normalized = value if isinstance(value, dict) else {}
    if signature is not None:
        _JSON_CACHE[path] = (signature, normalized)
    return deepcopy(normalized)


def load_base_workflow() -> dict[str, Any]:
    return _load_json_dict_cached(ANIMA_WORKFLOW_PATH, strict=True)


def load_anima_mapping() -> dict[str, Any]:
    return _load_json_dict_cached(ANIMA_MAPPING_PATH, strict=False)


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def model_sampling_shift_metadata(request: dict[str, Any] | None = None, workflow: dict[str, Any] | None = None) -> dict[str, Any]:
    mapping = load_anima_mapping()
    model_sampling = mapping.get("model_sampling") if isinstance(mapping.get("model_sampling"), dict) else {}
    node_id = str(model_sampling.get("node_id") or "")
    input_name = str(model_sampling.get("input") or "shift")
    class_type = str(model_sampling.get("class_type") or "ModelSamplingAuraFlow")
    warnings: list[str] = []
    if workflow is None:
        workflow = load_base_workflow()
    node = workflow.get(node_id) if node_id else None
    inputs = node.get("inputs") if isinstance(node, dict) else None
    workflow_value = _float_or_none(inputs.get(input_name)) if isinstance(inputs, dict) else None
    mapping_default = _float_or_none(model_sampling.get("fixed"))
    default = workflow_value if workflow_value is not None else mapping_default
    if default is None:
        default = 4.0
        warnings.append("ModelSamplingAuraFlow shift default was not found; using fallback 4.0.")
    requested_raw = request.get("shift") if isinstance(request, dict) else None
    requested = _float_or_none(requested_raw)
    if requested is None and requested_raw not in (None, ""):
        warnings.append(f"Invalid shift value ignored: {requested_raw}")
    supported = bool(
        node_id
        and isinstance(node, dict)
        and str(node.get("class_type") or class_type) == class_type
        and isinstance(inputs, dict)
        and input_name in inputs
    )
    if not node_id:
        warnings.append("model_sampling node_id is missing from anima_mapping.json.")
    elif not isinstance(node, dict):
        warnings.append(f"ModelSamplingAuraFlow node {node_id} was not found in the workflow.")
    elif not isinstance(inputs, dict) or input_name not in inputs:
        warnings.append(f"ModelSamplingAuraFlow input {input_name} was not found in node {node_id}.")
    shift = requested if requested is not None else default
    return {
        "supported": supported,
        "node_class": class_type,
        "node_id": node_id,
        "input_name": input_name,
        "current_workflow_value": workflow_value,
        "default": default,
        "shift": shift,
        "shift_source": "request" if requested is not None else "workflow",
        "warnings": warnings,
    }


def apply_model_sampling_shift(workflow: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    info = model_sampling_shift_metadata(request, workflow)
    if not info.get("supported"):
        return info
    node = workflow[str(info["node_id"])]
    node["inputs"][str(info["input_name"])] = float(info["shift"])
    return info

def build_workflow(request: dict[str, Any], prompts: dict[str, Any] | None = None) -> dict[str, Any]:
    from .detailer import apply_face_detailer, apply_hand_detailer

    if prompts is None:
        prompts = build_prompts(request)
    workflow = load_base_workflow()
    sample_mode = is_lora_sample_mode(request)
    model = str(request.get("model") or (LORA_SAMPLE_MODEL_NAME if sample_mode else "Anima\\anima-preview3-base.safetensors"))
    text_encoder = str(request.get("text_encoder") or "qwen_3_06b_base.safetensors")
    vae = str(request.get("vae") or "qwen_image_vae.safetensors")
    sampler = str(request.get("sampler") or ("euler" if sample_mode else "er_sde"))
    scheduler = str(request.get("scheduler") or "simple")
    steps = int(request.get("steps") or (30 if sample_mode else 32))
    cfg = float(request.get("cfg") or (4.0 if sample_mode else 4.5))
    width = int(request.get("width") or 1024)
    height = int(request.get("height") or (1024 if sample_mode else 1536))
    seed = int(prompts["seed"])

    workflow["44"]["inputs"]["model_name"] = model
    workflow["45"]["inputs"]["clip_name"] = text_encoder
    workflow["15"]["inputs"]["vae_name"] = vae
    workflow["11"]["inputs"]["text"] = prompts["positive"]
    workflow["12"]["inputs"]["text"] = prompts["negative"]
    workflow["28"]["inputs"]["width"] = width
    workflow["28"]["inputs"]["height"] = height
    workflow["28"]["inputs"]["batch_size"] = 1
    workflow["19"]["inputs"]["seed"] = seed
    workflow["19"]["inputs"]["steps"] = steps
    workflow["19"]["inputs"]["cfg"] = cfg
    workflow["19"]["inputs"]["sampler_name"] = sampler
    workflow["19"]["inputs"]["scheduler"] = scheduler
    workflow["19"]["inputs"]["denoise"] = float(request.get("denoise") or 1.0)
    method = infer_anima_generation_method(request)
    workflow["1"]["inputs"]["filename_prefix"] = build_output_prefix(
        panel_id="anima",
        generation_method=method,
        original_prefix="Anima",
    )
    apply_model_sampling_shift(workflow, request)
    previous_model = apply_official_loras(workflow, request)
    apply_catalog_loras(workflow, request, previous_model)
    apply_hires_fix(workflow, request)
    apply_image_to_image(workflow, request)
    apply_reference_assist(workflow, request)
    apply_reference_modules(workflow, request)
    apply_face_detailer(workflow, request, seed)
    apply_hand_detailer(workflow, request, seed)
    return workflow

def build_prompt_payload(request: dict[str, Any], client_id: str) -> dict[str, Any]:
    return {"prompt": build_workflow(request), "client_id": client_id}


def build_prompt_payload_with_prompts(request: dict[str, Any], client_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    prompts = build_prompts(request)
    return {"prompt": build_workflow(request, prompts=prompts), "client_id": client_id}, prompts
