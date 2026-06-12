from __future__ import annotations

from copy import deepcopy
import json
import math
import re
from typing import Any

from ._shared_utils import compact_join, next_node_id, normalize_lora_strengths, sanitize_prompt_text
from .anima_adapter import catalog, generate_seed
from .config import (
    ANIMA_HIGHRES_LORA_NAME,
    ANIMA_TURBO_LORA_V01_NAME,
    ANIMA_TURBO_LORA_V02_NAME,
    ANIMA_MAPPING_PATH,
    ANIMA_WORKFLOW_PATH,
    COMFYUI_LORA_DIRS,
    ROOT_DIR,
)
from .dynamic_prompt import expand_dynamic_prompt
from .face_detailer import add_face_detailer_to_workflow, face_detailer_seed, sanitize_face_detailer_settings
from .output_organizer import build_output_prefix, infer_anima_generation_method
from .reference_modules import apply_outfit_reference_to_workflow, apply_pose_reference_to_workflow


DYNAMIC_WILDCARD_CONFIG_DIR = ROOT_DIR / "config" / "dynamic_prompt_wildcards"
DYNAMIC_WILDCARD_USER_DIR = ROOT_DIR / "user_data" / "dynamic_prompt_wildcards"


QUALITY_PRESETS: dict[str, str] = {
    "standard": "masterpiece, best quality, score_7",
    "high": "masterpiece, best quality, high quality, highly detailed, score_8, score_7",
    "character_check": "best quality, clean character design, clear face, full body",
}

RATING_TAGS: dict[str, str] = {
    "safe": "safe",
    "sensitive": "sensitive",
    "nsfw": "nsfw",
    "explicit": "explicit",
}

NEGATIVE_PRESETS: dict[str, str] = {
    "anima_recommended": "score_1, score_2, score_3, watermark, signature, artist name, loli, child, teen, muscular woman, peeing, blood, worst quality, low quality, blurry, jpeg artifacts, sepia",
    "light": "low quality, blurry, bad anatomy",
    "strong": "worst quality, low quality, bad anatomy, bad hands, extra fingers, missing fingers, text, logo, watermark, artist name",
    "logo_watermark": "text, logo, watermark, signature, artist name, jpeg artifacts",
    "hands_eyes": "bad hands, extra fingers, missing fingers, fused fingers, bad eyes, asymmetrical eyes",
    "low_quality": "worst quality, low quality, blurry, noisy, jpeg artifacts",
}

LORA_SAMPLE_WORKFLOW_MODE = "anima_lora_sample"
LORA_SAMPLE_MODEL_NAME = "Anima\\anima-base-v1.0.safetensors"
LORA_SAMPLE_NEGATIVE = "worst quality, low quality, score_1, score_2, score_3, artist name, text, watermark, logo"


def is_lora_sample_mode(request: dict[str, Any]) -> bool:
    return str(request.get("workflow_mode") or "").strip() == LORA_SAMPLE_WORKFLOW_MODE


def find_lora_file(name: str) -> str:
    for directory in COMFYUI_LORA_DIRS:
        path = directory / name
        if path.exists():
            return str(path)
    return ""


def comfy_lora_name(name: str) -> str:
    return name.replace("/", "\\")


def resolve_official_loras(request: dict[str, Any]) -> dict[str, Any]:
    if is_lora_sample_mode(request):
        return {
            "highres": {"enabled": False, "file": ANIMA_HIGHRES_LORA_NAME, "path": "", "strength": 0.0},
            "turbo": {
                "enabled": False,
                "file": ANIMA_TURBO_LORA_V02_NAME,
                "path": "",
                "version": "v0.2",
                "strength": 0.0,
                "preset_applied": False,
            },
        }
    official = request.get("official_loras") or {}
    highres = official.get("highres") if isinstance(official.get("highres"), dict) else {}
    turbo = official.get("turbo") if isinstance(official.get("turbo"), dict) else {}
    turbo_v02_path = find_lora_file(ANIMA_TURBO_LORA_V02_NAME)
    turbo_v01_path = find_lora_file(ANIMA_TURBO_LORA_V01_NAME)
    requested_version = str(turbo.get("version") or "auto")
    if requested_version == "v0.1":
        turbo_name = ANIMA_TURBO_LORA_V01_NAME
        turbo_path = turbo_v01_path
    elif requested_version == "v0.2":
        turbo_name = ANIMA_TURBO_LORA_V02_NAME
        turbo_path = turbo_v02_path
    else:
        turbo_name = ANIMA_TURBO_LORA_V02_NAME if turbo_v02_path else ANIMA_TURBO_LORA_V01_NAME
        turbo_path = turbo_v02_path or turbo_v01_path
    return {
        "highres": {
            "enabled": bool(highres.get("enabled")),
            "file": ANIMA_HIGHRES_LORA_NAME,
            "path": find_lora_file(ANIMA_HIGHRES_LORA_NAME),
            "strength": max(0.0, min(1.0, float(highres.get("strength") or 0.6))),
        },
        "turbo": {
            "enabled": bool(turbo.get("enabled")),
            "file": turbo_name,
            "path": turbo_path,
            "version": "v0.2" if turbo_name == ANIMA_TURBO_LORA_V02_NAME else "v0.1",
            "strength": max(0.0, min(1.0, float(turbo.get("strength") or 0.6))),
            "preset_applied": bool(turbo.get("preset_applied")),
        },
    }


def official_lora_summary(request: dict[str, Any]) -> dict[str, Any]:
    resolved = resolve_official_loras(request)
    return {
        "highres": {
            "enabled": resolved["highres"]["enabled"],
            "file": resolved["highres"]["file"] if resolved["highres"]["enabled"] else "",
            "found": bool(resolved["highres"]["path"]),
            "strength": resolved["highres"]["strength"],
        },
        "turbo": {
            "enabled": resolved["turbo"]["enabled"],
            "file": resolved["turbo"]["file"] if resolved["turbo"]["enabled"] else "",
            "found": bool(resolved["turbo"]["path"]),
            "version": resolved["turbo"]["version"],
            "strength": resolved["turbo"]["strength"],
            "preset_applied": resolved["turbo"]["preset_applied"],
        },
    }


def normalize_lora_application(value: Any) -> str:
    text = str(value or "model_clip").strip().lower()
    if text in {"off", "none", "disabled"}:
        return "off"
    if text in {"base", "model", "model_only"}:
        return "model_only"
    return "model_clip"


def apply_official_loras(workflow: dict[str, Any], request: dict[str, Any]) -> list[Any]:
    resolved = resolve_official_loras(request)
    previous_model: list[Any] = ["44", 0]
    next_node_id = 9001
    for key in ("highres", "turbo"):
        item = resolved[key]
        if not item["enabled"]:
            continue
        if not item["path"]:
            raise ValueError(f"Official ANIMA LoRA file is missing: {item['file']}")
        node_id = str(next_node_id)
        workflow[node_id] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": previous_model,
                "lora_name": item["file"],
                "strength_model": item["strength"],
            },
        }
        previous_model = [node_id, 0]
        next_node_id += 1
    workflow["46"]["inputs"]["model"] = previous_model
    return previous_model


def apply_catalog_loras(workflow: dict[str, Any], request: dict[str, Any], previous_model: list[Any]) -> list[Any]:
    next_node_id = 9051
    previous_clip: list[Any] = ["45", 0]
    for raw in request.get("loras", []) or []:
        if not isinstance(raw, dict):
            continue
        raw = normalize_lora_strengths(raw)
        application = normalize_lora_application(raw.get("application", raw.get("mode")))
        if raw.get("enabled") is False or application == "off":
            continue
        lora_name = str(raw.get("name") or raw.get("relative_path") or "").strip()
        if not lora_name:
            continue
        node_id = str(next_node_id)
        if application == "model_only":
            workflow[node_id] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": previous_model,
                    "lora_name": comfy_lora_name(lora_name),
                    "strength_model": raw["strength_model"],
                },
            }
            previous_model = [node_id, 0]
        else:
            workflow[node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": previous_model,
                    "clip": previous_clip,
                    "lora_name": comfy_lora_name(lora_name),
                    "strength_model": raw["strength_model"],
                    "strength_clip": raw["strength_clip"],
                },
            }
            previous_model = [node_id, 0]
            previous_clip = [node_id, 1]
        next_node_id += 1
    workflow["46"]["inputs"]["model"] = previous_model
    workflow["11"]["inputs"]["clip"] = previous_clip
    workflow["12"]["inputs"]["clip"] = previous_clip
    return previous_model


def load_base_workflow() -> dict[str, Any]:
    return json.loads(ANIMA_WORKFLOW_PATH.read_text(encoding="utf-8"))


def load_anima_mapping() -> dict[str, Any]:
    try:
        value = json.loads(ANIMA_MAPPING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


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


def round_to_multiple(value: float, multiple: int = 8) -> int:
    if value <= 0:
        return multiple
    return max(multiple, int(round(value / multiple) * multiple))


def compute_hires_size(request: dict[str, Any]) -> dict[str, Any]:
    base_width = int(request.get("width") or 1024)
    base_height = int(request.get("height") or 1536)
    hires_fix = request.get("hires_fix") or {}
    enabled = bool(hires_fix.get("enabled"))
    factor = float(hires_fix.get("upscale_factor") or 1.0)
    target_width = int(hires_fix.get("target_width") or 0)
    target_height = int(hires_fix.get("target_height") or 0)
    if not enabled:
        factor = 1.0
        final_width = base_width
        final_height = base_height
    elif target_width > 0 and target_height > 0:
        final_width = round_to_multiple(target_width)
        final_height = round_to_multiple(target_height)
        factor = max(final_width / base_width, final_height / base_height)
    else:
        factor = factor if math.isfinite(factor) and factor > 1.0 else 1.0
        final_width = round_to_multiple(base_width * factor)
        final_height = round_to_multiple(base_height * factor)
    return {
        "base_width": base_width,
        "base_height": base_height,
        "enabled": enabled,
        "factor": factor,
        "target_width": target_width or None,
        "target_height": target_height or None,
        "final_width": final_width,
        "final_height": final_height,
    }


def escape_standard_character_tag(tag: str) -> str:
    return tag.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")


def format_weighted(tag: str, weight: float) -> str:
    tag = tag.strip()
    if not tag:
        return ""
    if abs(float(weight) - 1.0) < 0.0001:
        return tag
    return f"({tag}:{weight:g})"


def apply_dynamic_prompts(request: dict[str, Any], positive: str, negative: str, seed: int) -> tuple[str, str, dict[str, Any] | None]:
    settings = request.get("dynamic_prompt") if isinstance(request.get("dynamic_prompt"), dict) else {}
    enabled = bool(settings.get("enabled"))
    result = expand_dynamic_prompt(
        positive_prompt=positive,
        negative_prompt=negative,
        seed=settings.get("wildcard_seed", seed),
        enabled=enabled,
        config_dir=DYNAMIC_WILDCARD_CONFIG_DIR,
        user_dir=DYNAMIC_WILDCARD_USER_DIR,
    )
    if not enabled:
        return positive, negative, None
    return str(result.get("expanded_positive_prompt") or ""), str(result.get("expanded_negative_prompt") or ""), result


def split_prompt_terms(text: str) -> list[str]:
    return [item.strip() for item in re.split(r",|\n", text or "") if item.strip()]


def character_metadata(entry: Any, slot: int, role: str = "") -> dict[str, Any]:
    source = "original_character" if getattr(entry, "kind", "") == "original" else "saa_csv"
    return {
        "slot": slot,
        "source": source,
        "id": getattr(entry, "id", "") or getattr(entry, "display_name", ""),
        "display_name": getattr(entry, "display_name", ""),
        "role": role,
        "prompt_tag": getattr(entry, "prompt_tag", ""),
        "trigger_words": list(getattr(entry, "trigger_words", None) or []),
        "identity_prompt": getattr(entry, "identity_prompt", ""),
        "negative_guard": getattr(entry, "negative_guard", ""),
        "default_lora": getattr(entry, "default_lora", None),
    }


def original_identity_sentence(entry: Any, role: str) -> str:
    name = getattr(entry, "display_name", "") or "The original character"
    identity = getattr(entry, "identity_prompt", "") or f"{name} is an original anime-style character."
    if role == "left":
        return f"The girl on the left is {name}, an original anime-style character."
    if role == "right":
        return f"The girl on the right is {name}, an original anime-style character."
    if role and role != "main":
        return f"{name} is the {role} character."
    return identity


def build_character_parts(request: dict[str, Any], seed: int) -> tuple[list[str], list[str], list[dict[str, Any]], list[str]]:
    character_values = [
        request.get("character1", "Random"),
        request.get("character2", "None"),
        request.get("character3", "None"),
    ]
    roles = [
        str(request.get("character1_role") or "main"),
        str(request.get("character2_role") or "left"),
        str(request.get("character3_role") or "right"),
    ]
    weights = [
        float(request.get("character1_weight", 1.0)),
        float(request.get("character2_weight", 1.0)),
        float(request.get("character3_weight", 1.0)),
    ]
    tags: list[str] = []
    names: list[str] = []
    metadata: list[dict[str, Any]] = []
    natural_parts: list[str] = []
    for index, value in enumerate(character_values):
        tag, name, entry = catalog.resolve_character_entry(str(value), index, seed, original=False)
        if not tag:
            continue
        role = roles[index]
        prompt_tag = tag if getattr(entry, "kind", "") == "original" else escape_standard_character_tag(tag)
        weighted = format_weighted(prompt_tag, weights[index])
        tags.append(weighted)
        names.append(f"{name} ({role})" if role and role != "main" else name)
        if entry:
            metadata.append(character_metadata(entry, index + 1, role))
            if getattr(entry, "kind", "") == "original":
                natural_parts.append(original_identity_sentence(entry, role))
    original_value = request.get("original_character", "None")
    original_tag, original_name, original_entry = catalog.resolve_character_entry(str(original_value), 3, seed, original=True)
    if original_tag:
        original_weight = float(request.get("original_weight", 1.0))
        tags.append(format_weighted(original_tag, original_weight))
        names.append(original_name)
        if original_entry:
            metadata.append(character_metadata(original_entry, 4, "original"))
            natural_parts.append(original_identity_sentence(original_entry, "main"))
    return tags, names, metadata, natural_parts


def build_natural_description(character_names: list[str], request: dict[str, Any], natural_parts: list[str] | None = None) -> str:
    manual = str(request.get("natural_description") or "").strip()
    parts = [item for item in natural_parts or [] if item]
    if manual:
        return " ".join([*parts, manual])
    if parts:
        return " ".join(parts)
    if not character_names:
        return ""
    if len(character_names) == 1:
        return f"An anime illustration of {character_names[0]} in a clean, expressive composition."
    lines = ["An anime illustration with multiple characters."]
    for name in character_names:
        lines.append(f"{name} is clearly separated by position and silhouette.")
    return " ".join(lines)


def build_prompts(request: dict[str, Any]) -> dict[str, Any]:
    if is_lora_sample_mode(request):
        return build_lora_sample_prompts(request)

    seed = generate_seed(request.get("seed"))
    character_tags, character_names, character_meta, natural_parts = build_character_parts(request, seed)
    rating = str(request.get("rating") or "safe").lower()
    rating_tag = RATING_TAGS.get(rating, "safe")
    quality = QUALITY_PRESETS.get(str(request.get("quality_preset") or "standard"), str(request.get("quality_preset") or ""))
    meta = str(request.get("meta_prompt") or "anime illustration").strip()
    year = str(request.get("year_prompt") or "").strip()
    outfit = str(request.get("outfit_prompt") or "").strip()
    expression = str(request.get("expression_prompt") or "").strip()
    pose = str(request.get("pose_prompt") or "").strip()
    background = str(request.get("background_prompt") or "").strip()
    camera = str(request.get("camera_prompt") or "").strip()
    lighting = str(request.get("lighting_prompt") or "").strip()
    positive = str(request.get("positive_prompt") or "").strip()
    common = str(request.get("common_prompt") or "").strip()
    natural = build_natural_description(character_names, request, natural_parts)
    prompt_ban = str(request.get("prompt_ban") or "").strip()

    people_tag = ""
    count = len(character_tags)
    if count == 1:
        people_tag = "1girl"
    elif count > 1:
        people_tag = f"{count}girls"

    positive_terms = [
        quality,
        meta,
        year,
        rating_tag,
        people_tag,
        *character_tags,
        common,
        outfit,
        expression,
        pose,
        background,
        camera,
        lighting,
        natural,
        positive,
    ]
    full_positive = sanitize_prompt_text(compact_join(positive_terms))
    if prompt_ban:
        for term in [item.strip() for item in prompt_ban.split(",") if item.strip()]:
            full_positive = re.sub(re.escape(term), "", full_positive, flags=re.IGNORECASE)
        full_positive = sanitize_prompt_text(full_positive)

    negative_preset_key = str(request.get("negative_preset") or "anima_recommended")
    negative_preset = NEGATIVE_PRESETS.get(negative_preset_key, "")
    negative_manual = str(request["negative_prompt_raw"] if "negative_prompt_raw" in request else request.get("negative_prompt", "")).strip()
    negative_mode = str(request.get("negative_prompt_mode") or "append")
    if negative_mode in {"preset", "source"}:
        negative_mode = "preset"
        full_negative = negative_preset
    elif negative_mode == "custom":
        full_negative = negative_manual
    else:
        negative_mode = "append"
        full_negative = compact_join([negative_preset, negative_manual])

    full_positive, full_negative, dynamic_prompt = apply_dynamic_prompts(request, full_positive, full_negative, seed)

    prompts = {
        "seed": seed,
        "positive": full_positive,
        "negative": full_negative,
        "negative_mode": negative_mode,
        "negative_preset": negative_preset_key,
        "characters": character_names,
        "character_metadata": character_meta,
        "negative_guards": [item.get("negative_guard", "") for item in character_meta if item.get("negative_guard")],
        "rating": rating,
        "natural_description": natural,
    }
    if dynamic_prompt:
        prompts["dynamic_prompt"] = dynamic_prompt
    return prompts


def build_lora_sample_prompts(request: dict[str, Any]) -> dict[str, Any]:
    seed = generate_seed(request.get("seed"))
    character_tags, character_names, character_meta, _natural_parts = build_character_parts(request, seed)
    positive = str(request.get("positive_prompt") or "").strip()
    if not positive:
        positive = compact_join([*character_tags, str(request.get("common_prompt") or "").strip()])
    positive = sanitize_prompt_text(positive)
    prompt_ban = str(request.get("prompt_ban") or "").strip()
    if prompt_ban:
        for term in [item.strip() for item in prompt_ban.split(",") if item.strip()]:
            positive = re.sub(re.escape(term), "", positive, flags=re.IGNORECASE)
        positive = sanitize_prompt_text(positive)

    negative_preset_key = str(request.get("negative_preset") or "anima_recommended")
    negative_preset = NEGATIVE_PRESETS.get(negative_preset_key, "")
    negative_manual = str(request["negative_prompt_raw"] if "negative_prompt_raw" in request else request.get("negative_prompt", "")).strip()
    negative_mode = str(request.get("negative_prompt_mode") or "custom")
    if negative_mode in {"preset", "source"}:
        negative_mode = "preset"
        full_negative = negative_preset or LORA_SAMPLE_NEGATIVE
    elif negative_mode == "append":
        full_negative = compact_join([negative_preset, negative_manual])
    else:
        negative_mode = "custom"
        full_negative = negative_manual or LORA_SAMPLE_NEGATIVE

    positive, full_negative, dynamic_prompt = apply_dynamic_prompts(request, positive, full_negative, seed)

    prompts = {
        "seed": seed,
        "positive": positive,
        "negative": full_negative,
        "negative_mode": negative_mode,
        "negative_preset": negative_preset_key,
        "characters": character_names,
        "character_metadata": character_meta,
        "negative_guards": [item.get("negative_guard", "") for item in character_meta if item.get("negative_guard")],
        "rating": str(request.get("rating") or "safe").lower(),
        "natural_description": "",
    }
    if dynamic_prompt:
        prompts["dynamic_prompt"] = dynamic_prompt
    return prompts


def build_workflow(request: dict[str, Any]) -> dict[str, Any]:
    prompts = build_prompts(request)
    workflow = deepcopy(load_base_workflow())
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
    apply_image_to_image(workflow, request)
    apply_reference_assist(workflow, request)
    apply_reference_modules(workflow, request)
    apply_face_detailer(workflow, request, seed)
    return workflow


def apply_image_to_image(workflow: dict[str, Any], request: dict[str, Any]) -> None:
    i2i = request.get("image_to_image") if isinstance(request.get("image_to_image"), dict) else {}
    if not i2i.get("apply_to_payload"):
        return
    image_name = str((i2i.get("comfyui_image") or {}).get("name") or i2i.get("image_name") or i2i.get("prepared_filename") or "")
    if not image_name:
        i2i["apply_to_payload"] = False
        i2i["unsupported_reason"] = "missing ComfyUI i2i image"
        request["image_to_image"] = i2i
        return
    denoise = max(0.01, min(1.0, float(i2i.get("denoise") or 0.45)))
    load_id = next_node_id(workflow)
    encode_id = next_node_id(workflow, int(load_id) + 1)
    workflow[load_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": image_name},
        "_meta": {"title": "Image to Image Source"},
    }
    workflow[encode_id] = {
        "class_type": "VAEEncode",
        "inputs": {"pixels": [load_id, 0], "vae": ["15", 0]},
        "_meta": {"title": "Image to Image VAE Encode"},
    }
    workflow["19"]["inputs"]["latent_image"] = [encode_id, 0]
    workflow["19"]["inputs"]["denoise"] = denoise
    i2i.update(
        {
            "applied": True,
            "mode": "generation",
            "denoise": denoise,
            "image_name": image_name,
            "sampler_node": "19",
            "load_image_node": load_id,
            "latent_node": encode_id,
        }
    )
    request["image_to_image"] = i2i


def apply_reference_modules(workflow: dict[str, Any], request: dict[str, Any]) -> None:
    modules = request.get("reference_modules") if isinstance(request.get("reference_modules"), dict) else {}
    apply_outfit_reference_to_workflow(workflow, modules, sampler_ids=["19"], next_node_id=next_node_id)
    apply_pose_reference_to_workflow(workflow, modules, sampler_ids=["19"], next_node_id=next_node_id)
    request["reference_modules"] = modules


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


def apply_reference_assist(workflow: dict[str, Any], request: dict[str, Any]) -> None:
    ref = request.get("reference_assist") if isinstance(request.get("reference_assist"), dict) else {}
    if not ref.get("apply_to_payload"):
        return
    image_name = str((ref.get("comfyui_image") or {}).get("name") or ref.get("image_name") or "")
    controlnet_model = str(ref.get("controlnet_model") or "")
    if not image_name or not controlnet_model:
        return
    apply_node_type = str(ref.get("apply_node_type") or "ControlNetApplyAdvanced")
    strength = max(0.0, min(1.0, float(ref.get("strength") or 0.25)))
    start_percent = max(0.0, min(1.0, float(ref.get("start_percent") or 0.0)))
    end_percent = max(0.0, min(1.0, float(ref.get("end_percent") or 0.65)))
    load_id = next_node_id(workflow)
    control_id = next_node_id(workflow, int(load_id) + 1)
    workflow[load_id] = {
        "inputs": {"image": image_name},
        "class_type": "LoadImage",
        "_meta": {"title": "Reference Assist Image"},
    }
    workflow[control_id] = {
        "inputs": {"control_net_name": controlnet_model},
        "class_type": "ControlNetLoader",
        "_meta": {"title": "Reference Assist ControlNet"},
    }
    control_output: list[Any] = [control_id, 0]
    if ref.get("has_union_type"):
        union_id = next_node_id(workflow, int(control_id) + 1)
        workflow[union_id] = {
            "inputs": {"control_net": [control_id, 0], "type": str(ref.get("union_type") or "auto")},
            "class_type": "SetUnionControlNetType",
            "_meta": {"title": "Reference Assist Union Type"},
        }
        control_output = [union_id, 0]
    sampler = workflow.get("19")
    inputs = sampler.get("inputs") if isinstance(sampler, dict) else None
    if not isinstance(inputs, dict) or "positive" not in inputs or "negative" not in inputs:
        return
    apply_id = next_node_id(workflow, int(control_output[0]) + 1)
    if apply_node_type == "ControlNetApplyAdvanced":
        apply_inputs: dict[str, Any] = {
            "positive": inputs.get("positive"),
            "negative": inputs.get("negative"),
            "control_net": control_output,
            "image": [load_id, 0],
            "strength": strength,
            "start_percent": start_percent,
            "end_percent": end_percent,
        }
        positive_output = [apply_id, 0]
        negative_output = [apply_id, 1]
    else:
        apply_inputs = {
            "conditioning": inputs.get("positive"),
            "control_net": control_output,
            "image": [load_id, 0],
            "strength": strength,
        }
        positive_output = [apply_id, 0]
        negative_output = inputs.get("negative")
    workflow[apply_id] = {
        "inputs": apply_inputs,
        "class_type": apply_node_type,
        "_meta": {"title": "Reference Assist Apply"},
    }
    inputs["positive"] = positive_output
    inputs["negative"] = negative_output


def build_prompt_payload(request: dict[str, Any], client_id: str) -> dict[str, Any]:
    return {"prompt": build_workflow(request), "client_id": client_id}


def build_face_detailer_postprocess_payload(request: dict[str, Any], client_id: str, image_name: str) -> dict[str, Any]:
    return {"prompt": build_face_detailer_postprocess_workflow(request, image_name), "client_id": client_id}
