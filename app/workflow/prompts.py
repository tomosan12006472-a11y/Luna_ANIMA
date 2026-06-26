from __future__ import annotations

import re
from typing import Any

from .._shared_utils import compact_join, sanitize_prompt_text
from ..anima_adapter import catalog, generate_seed
from ..character_names import contains_cjk, display_name_ja, prompt_safe_character_name
from ..config import ROOT_DIR
from ..dynamic_prompt import expand_dynamic_prompt
from ..prompt_random_collect import prompt_random_collect_tags


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


def quality_prompt_for_request(request: dict[str, Any]) -> str:
    preset = str(request.get("quality_preset") or "standard")
    overrides = request.get("quality_prompt_overrides")
    if isinstance(overrides, dict) and preset in overrides:
        return str(overrides.get(preset) or "").strip()
    return QUALITY_PRESETS.get(preset, preset).strip()


def rating_prompt_for_request(request: dict[str, Any]) -> str:
    rating = str(request.get("rating") or "safe").lower()
    overrides = request.get("rating_prompt_overrides")
    if isinstance(overrides, dict) and rating in overrides:
        return str(overrides.get(rating) or "").strip()
    return RATING_TAGS.get(rating, rating).strip()

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

def escape_standard_character_tag(tag: str) -> str:
    return tag.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")


def escape_prompt_parentheses(text: str) -> str:
    text = re.sub(r"(?<!\\)\(", r"\\(", text)
    return re.sub(r"(?<!\\)\)", r"\\)", text)


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
    source = "original_character" if getattr(entry, "kind", "") == "original" else str(getattr(entry, "source", "") or "saa_csv")
    display_name = getattr(entry, "display_name", "")
    prompt_tag = getattr(entry, "prompt_tag", "")
    return {
        "slot": slot,
        "source": source,
        "id": getattr(entry, "id", "") or getattr(entry, "display_name", ""),
        "display_name": display_name_ja(display_name, prompt_tag),
        "display_name_original": display_name,
        "role": role,
        "prompt_tag": prompt_tag,
        "prompt_safe_name": prompt_safe_character_name(display_name, prompt_tag),
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


def build_character_parts(
    request: dict[str, Any], seed: int
) -> tuple[list[str], list[str], list[dict[str, Any]], list[str], list[dict[str, str]]]:
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
    natural_names: list[dict[str, str]] = []
    for index, value in enumerate(character_values):
        tag, name, entry = catalog.resolve_character_entry(str(value), index, seed, original=False)
        if not tag:
            continue
        if not entry and contains_cjk(tag):
            continue
        role = roles[index]
        prompt_tag = tag if getattr(entry, "kind", "") == "original" else escape_standard_character_tag(tag)
        weighted = format_weighted(prompt_tag, weights[index])
        safe_name = prompt_safe_character_name(name, tag)
        display_name = display_name_ja(name, tag)
        tags.append(weighted)
        names.append(f"{display_name} ({role})" if role and role != "main" else display_name)
        if safe_name:
            natural_names.append({"name": safe_name, "role": role})
        if entry:
            metadata.append(character_metadata(entry, index + 1, role))
            if getattr(entry, "kind", "") == "original":
                natural_parts.append(original_identity_sentence(entry, role))
    original_value = request.get("original_character", "None")
    original_tag, original_name, original_entry = catalog.resolve_character_entry(str(original_value), 3, seed, original=True)
    if original_tag:
        original_weight = float(request.get("original_weight", 1.0))
        tags.append(format_weighted(original_tag, original_weight))
        names.append(display_name_ja(original_name, original_tag))
        safe_name = prompt_safe_character_name(original_name, original_tag)
        if safe_name:
            natural_names.append({"name": safe_name, "role": "main"})
        if original_entry:
            metadata.append(character_metadata(original_entry, 4, "original"))
            natural_parts.append(original_identity_sentence(original_entry, "main"))
    return tags, names, metadata, natural_parts, natural_names


def _natural_character_name_and_role(character: Any) -> tuple[str, str]:
    if isinstance(character, dict):
        name = str(character.get("name") or "").strip()
        role = str(character.get("role") or "").strip().lower()
    else:
        text = str(character or "").strip()
        match = re.fullmatch(r"(.+?)\s+\((left|right|main|original)\)", text, flags=re.IGNORECASE)
        name = match.group(1).strip() if match else text
        role = match.group(2).lower() if match else ""
    return escape_prompt_parentheses(name), role


def _natural_character_subject(role: str, index: int) -> str:
    if role == "left":
        return "the left girl"
    if role == "right":
        return "the right girl"
    if role == "main":
        return "the main girl"
    if role:
        return f"the {role} character"
    if index == 0:
        return "the left girl"
    if index == 1:
        return "the right girl"
    return f"girl {index + 1}"


def generated_natural_description(characters: list[Any]) -> str:
    if not characters:
        return ""
    natural_characters = [_natural_character_name_and_role(character) for character in characters]
    natural_characters = [(name, role) for name, role in natural_characters if name]
    if not natural_characters:
        return ""
    if len(natural_characters) == 1:
        return f"An anime illustration of {natural_characters[0][0]} in a clean, expressive composition."
    clauses = [
        f"{_natural_character_subject(role, index)} is {name}"
        for index, (name, role) in enumerate(natural_characters)
    ]
    return f"An anime illustration with multiple characters, {', '.join(clauses)}."


def normalize_natural_description(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_generated_natural_description(value: str) -> bool:
    text = normalize_natural_description(value)
    if re.fullmatch(r"An anime illustration of .+ in a clean, expressive composition\.", text):
        return True
    if not text.startswith("An anime illustration with multiple characters"):
        return False
    return (
        " is clearly separated by position and silhouette." in text
        or re.search(r"\b(?:the )?(?:left|right|main) girl is ", text, flags=re.IGNORECASE) is not None
        or re.search(r"\bgirl \d+ is ", text, flags=re.IGNORECASE) is not None
    )


def build_natural_description(characters: list[Any], request: dict[str, Any], natural_parts: list[str] | None = None) -> str:
    manual = str(request.get("natural_description") or "").strip()
    parts = [item for item in natural_parts or [] if item]
    generated = generated_natural_description(characters)
    if manual and is_generated_natural_description(manual):
        if not characters:
            manual = ""
        elif normalize_natural_description(manual) != normalize_natural_description(generated):
            manual = ""
    if manual:
        return " ".join([*parts, manual])
    if parts:
        return " ".join(parts)
    return generated


def build_prompts(request: dict[str, Any]) -> dict[str, Any]:
    if is_lora_sample_mode(request):
        return build_lora_sample_prompts(request)

    seed = generate_seed(request.get("seed"))
    character_tags, character_names, character_meta, natural_parts, natural_names = build_character_parts(request, seed)
    rating = str(request.get("rating") or "safe").lower()
    rating_tag = rating_prompt_for_request(request)
    quality = quality_prompt_for_request(request)
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
    natural = build_natural_description(natural_names, request, natural_parts)
    prompt_ban = str(request.get("prompt_ban") or "").strip()
    random_collect = prompt_random_collect_tags(request)

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
        random_collect,
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
    character_tags, character_names, character_meta, _natural_parts, _natural_names = build_character_parts(request, seed)
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
