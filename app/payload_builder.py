from __future__ import annotations

from .config import (
    ANIMA_COLORFIX_LORA_NAME,
    ANIMA_HIGHRES_LORA_NAME,
    ANIMA_TURBO_LORA_V01_NAME,
    ANIMA_TURBO_LORA_V02_NAME,
    COMFYUI_LORA_DIRS,
    ROOT_DIR,
)
from .output_organizer import build_output_prefix
from .workflow import base as _base
from .workflow import detailer as _detailer
from .workflow import loras as _loras
from .workflow.base import (
    _float_or_none,
    apply_model_sampling_shift,
    build_prompt_payload as _build_prompt_payload,
    build_workflow as _build_workflow,
    load_anima_mapping,
    load_base_workflow,
    model_sampling_shift_metadata,
)
from .workflow.detailer import (
    add_hand_lllite_mask_to_workflow,
    apply_face_detailer,
    apply_hand_detailer,
    build_face_detailer_postprocess_payload as _build_face_detailer_postprocess_payload,
    build_face_detailer_postprocess_workflow as _build_face_detailer_postprocess_workflow,
    build_hand_detailer_postprocess_payload as _build_hand_detailer_postprocess_payload,
    build_hand_detailer_postprocess_workflow as _build_hand_detailer_postprocess_workflow,
)
from .workflow.hires import apply_hires_fix, compute_hires_size, round_to_multiple
from .workflow.i2i import apply_image_to_image
from .workflow.loras import (
    apply_catalog_loras as _apply_catalog_loras,
    apply_official_loras as _apply_official_loras,
    comfy_lora_name,
    find_lora_file as _find_lora_file,
    normalize_lora_application,
    official_lora_summary as _official_lora_summary,
    resolve_official_loras as _resolve_official_loras,
)
from .workflow.prompts import (
    DYNAMIC_WILDCARD_CONFIG_DIR,
    DYNAMIC_WILDCARD_USER_DIR,
    LORA_SAMPLE_MODEL_NAME,
    LORA_SAMPLE_NEGATIVE,
    LORA_SAMPLE_WORKFLOW_MODE,
    NEGATIVE_PRESETS,
    QUALITY_PRESETS,
    RATING_TAGS,
    apply_dynamic_prompts,
    build_character_parts,
    build_lora_sample_prompts,
    build_natural_description,
    build_prompts,
    character_metadata,
    escape_standard_character_tag,
    format_weighted,
    generated_natural_description,
    is_generated_natural_description,
    is_lora_sample_mode,
    normalize_natural_description,
    original_identity_sentence,
    quality_prompt_for_request,
    rating_prompt_for_request,
    split_prompt_terms,
)
from .workflow.reference import apply_reference_assist, apply_reference_modules


find_lora_file = _find_lora_file


def _sync_facade_overrides() -> None:
    _loras.find_lora_file = find_lora_file
    _base.build_output_prefix = build_output_prefix
    _detailer.build_output_prefix = build_output_prefix
    _base.apply_official_loras = apply_official_loras
    _base.apply_catalog_loras = apply_catalog_loras
    _detailer.apply_official_loras = apply_official_loras
    _detailer.apply_catalog_loras = apply_catalog_loras


def resolve_official_loras(request: dict[str, object]) -> dict[str, object]:
    _sync_facade_overrides()
    return _resolve_official_loras(request)


def official_lora_summary(request: dict[str, object]) -> dict[str, object]:
    _sync_facade_overrides()
    return _official_lora_summary(request)


def apply_official_loras(workflow: dict[str, object], request: dict[str, object]) -> list[object]:
    _sync_facade_overrides()
    return _apply_official_loras(workflow, request)


def apply_catalog_loras(workflow: dict[str, object], request: dict[str, object], previous_model: list[object]) -> list[object]:
    _sync_facade_overrides()
    return _apply_catalog_loras(workflow, request, previous_model)


def build_workflow(request: dict[str, object]) -> dict[str, object]:
    _sync_facade_overrides()
    return _build_workflow(request)


def build_prompt_payload(request: dict[str, object], client_id: str) -> dict[str, object]:
    _sync_facade_overrides()
    return _build_prompt_payload(request, client_id)


def build_face_detailer_postprocess_workflow(request: dict[str, object], image_name: str) -> dict[str, object]:
    _sync_facade_overrides()
    return _build_face_detailer_postprocess_workflow(request, image_name)


def build_hand_detailer_postprocess_workflow(request: dict[str, object], image_name: str) -> dict[str, object]:
    _sync_facade_overrides()
    return _build_hand_detailer_postprocess_workflow(request, image_name)


def build_face_detailer_postprocess_payload(request: dict[str, object], client_id: str, image_name: str) -> dict[str, object]:
    _sync_facade_overrides()
    return _build_face_detailer_postprocess_payload(request, client_id, image_name)


def build_hand_detailer_postprocess_payload(request: dict[str, object], client_id: str, image_name: str) -> dict[str, object]:
    _sync_facade_overrides()
    return _build_hand_detailer_postprocess_payload(request, client_id, image_name)


__all__ = [
    "ANIMA_COLORFIX_LORA_NAME",
    "ANIMA_HIGHRES_LORA_NAME",
    "ANIMA_TURBO_LORA_V01_NAME",
    "ANIMA_TURBO_LORA_V02_NAME",
    "COMFYUI_LORA_DIRS",
    "ROOT_DIR",
    "build_output_prefix",
    "DYNAMIC_WILDCARD_CONFIG_DIR",
    "DYNAMIC_WILDCARD_USER_DIR",
    "QUALITY_PRESETS",
    "RATING_TAGS",
    "NEGATIVE_PRESETS",
    "LORA_SAMPLE_WORKFLOW_MODE",
    "LORA_SAMPLE_MODEL_NAME",
    "LORA_SAMPLE_NEGATIVE",
    "quality_prompt_for_request",
    "rating_prompt_for_request",
    "is_lora_sample_mode",
    "find_lora_file",
    "comfy_lora_name",
    "resolve_official_loras",
    "official_lora_summary",
    "normalize_lora_application",
    "apply_official_loras",
    "apply_catalog_loras",
    "load_base_workflow",
    "load_anima_mapping",
    "_float_or_none",
    "model_sampling_shift_metadata",
    "apply_model_sampling_shift",
    "round_to_multiple",
    "compute_hires_size",
    "apply_hires_fix",
    "escape_standard_character_tag",
    "format_weighted",
    "apply_dynamic_prompts",
    "split_prompt_terms",
    "character_metadata",
    "original_identity_sentence",
    "build_character_parts",
    "generated_natural_description",
    "normalize_natural_description",
    "is_generated_natural_description",
    "build_natural_description",
    "build_prompts",
    "build_lora_sample_prompts",
    "build_workflow",
    "apply_image_to_image",
    "apply_reference_modules",
    "build_face_detailer_postprocess_workflow",
    "build_hand_detailer_postprocess_workflow",
    "apply_face_detailer",
    "add_hand_lllite_mask_to_workflow",
    "apply_hand_detailer",
    "apply_reference_assist",
    "build_prompt_payload",
    "build_face_detailer_postprocess_payload",
    "build_hand_detailer_postprocess_payload",
]
