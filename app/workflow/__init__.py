from __future__ import annotations

from .base import (
    apply_model_sampling_shift,
    build_prompt_payload,
    build_prompt_payload_with_prompts,
    build_workflow,
    load_anima_mapping,
    load_base_workflow,
    model_sampling_shift_metadata,
)
from .detailer import (
    add_hand_lllite_mask_to_workflow,
    apply_face_detailer,
    apply_hand_detailer,
    build_face_detailer_postprocess_payload,
    build_face_detailer_postprocess_workflow,
    build_hand_detailer_postprocess_payload,
    build_hand_detailer_postprocess_workflow,
)
from .hires import apply_hires_fix, compute_hires_size, round_to_multiple
from .i2i import apply_image_to_image
from .loras import (
    apply_catalog_loras,
    apply_official_loras,
    comfy_lora_name,
    find_lora_file,
    normalize_lora_application,
    official_lora_summary,
    resolve_official_loras,
)
from .prompts import (
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
from .reference import apply_reference_assist, apply_reference_modules
