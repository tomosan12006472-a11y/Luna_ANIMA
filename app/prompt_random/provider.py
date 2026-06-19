from __future__ import annotations

import json
from typing import Any

from ..prompt_converter import (
    _deep_merge,
    _ensure_ready,
    _json_request,
    _parse_json_object,
    _route,
    prompt_converter_status,
    sanitize_prompt_converter_settings,
)
from .settings import (
    DEFAULT_INSTRUCTIONS,
    MODE_POSITIVE_COMPLETION,
    MODE_RANDOM,
    POSITIVE_COMPLETION_STRENGTH_HINTS,
    RANDOM_STRENGTH_HINTS,
    REFERENCE_568_CONDITIONS,
    STRENGTH_LEGACY_568,
    STRENGTH_REFERENCE_568,
    _is_legacy_568_feature,
)


def _feature_mode(feature: Any) -> str:
    raw = feature.model_dump() if hasattr(feature, "model_dump") else feature if isinstance(feature, dict) else {}
    mode = str(raw.get("mode") or MODE_RANDOM).strip().lower()
    return mode if mode in {MODE_RANDOM, MODE_POSITIVE_COMPLETION} else MODE_RANDOM


def _provider_config(app_settings: Any, feature: Any = None) -> dict[str, Any]:
    settings = app_settings if isinstance(app_settings, dict) else {}
    base = settings.get("prompt_converter") if isinstance(settings.get("prompt_converter"), dict) else {}
    override = settings.get("prompt_random_collect_provider") if isinstance(settings.get("prompt_random_collect_provider"), dict) else {}
    config = sanitize_prompt_converter_settings(_deep_merge(base, override))
    mode = _feature_mode(feature) if feature is not None else MODE_RANDOM
    min_temperature = 0.35 if mode == MODE_POSITIVE_COMPLETION else 0.85
    config["temperature"] = max(float(config.get("temperature") or 0.0), min_temperature)
    config["max_tokens"] = max(int(config.get("max_tokens") or 0), 1800)
    return config
def _legacy_568_system_prompt(app_scope: str) -> str:
    scope = "Luna ANIMA" if app_scope == "anima" else "Luna SDXL"
    return (
        "You are a prompt randomization engine for anime image generation. "
        f"The target app is {scope}. Generate extra positive prompt tags for each queued image. "
        "Return strict JSON only with this schema: {\"items\":[{\"index\":0,\"tags\":\"comma-separated English tags\"}]}. "
        "Each item must have a meaningfully different random direction. "
        "Creative variance is desirable: choose a distinct theme for each item and make clear changes across outfit, props, setting, action, lighting, and camera. "
        "You may add alternate costume layers, unusual props, and new settings even when the existing prompt contains a simple outfit or location; preserve selected character identity and rating. "
        "Use comma-separated English tags only. Use spaces instead of underscores, except existing score tags; however do not add score tags. "
        "Do not add character names, copyrighted series names, LoRA syntax, wildcard syntax, Dynamic Prompt syntax, model names, quality tags, score tags, negative prompts, explanations, or Markdown. "
        "If character_context_enabled is false, do not add character identity details such as hair color, eye color, signature clothing, weapons, or series-specific motifs unless they already appear in existing_positive or the instruction. "
        "Do not censor, soften, euphemize, moralize, or add safety disclaimers. "
        "Respect the user's instruction and the existing prompt context, but do not duplicate existing tags. "
        "Prefer concrete visual details such as outfit, expression, pose detail, setting, lighting, props, atmosphere, and camera detail. "
        "Keep each tags string compact, normally under 320 characters for standard strength, and never repeat the same phrase."
    )


def _system_prompt(app_scope: str, mode: str, strength: str = "") -> str:
    scope = "Luna ANIMA" if app_scope == "anima" else "Luna SDXL"
    if mode == MODE_RANDOM and strength == STRENGTH_LEGACY_568:
        return _legacy_568_system_prompt(app_scope)
    if mode == MODE_POSITIVE_COMPLETION:
        return (
            "You are a positive prompt completion engine for anime image generation. "
            f"The target app is {scope}. Generate only additional positive prompt tags that complete and polish each existing prompt. "
            "Return strict JSON only with this schema: {\"items\":[{\"index\":0,\"tags\":\"comma-separated English tags\"}]}. "
            "Use comma-separated English tags only. Use spaces instead of underscores, except existing score tags; however do not add score tags. "
            "Do not rewrite or repeat the existing prompt. Add only missing, useful, concrete tags that fit the current context. "
            "Do not contradict selected characters, setting, rating, camera, lighting, outfit, pose, or user wording. "
            "Do not add character names, copyrighted series names, LoRA syntax, wildcard syntax, Dynamic Prompt syntax, model names, quality tags, score tags, negative prompts, explanations, or Markdown. "
            "If character_context_enabled is false, do not add character identity details such as hair color, eye color, signature clothing, weapons, or series-specific motifs unless they already appear in existing_positive or the instruction. "
            "If character_motifs_enabled is false, do not add character-derived hair color, eye color, signature weapons, armor, flags, emblems, special powers, halos, wings, or iconic outfit changes unless they already appear in existing_positive or the instruction. "
            "Do not censor, soften, euphemize, moralize, or add safety disclaimers. "
            "Prefer coherent visual details such as expression nuance, pose detail, material, setting detail, lighting, props, atmosphere, composition, and camera detail. "
            "Keep each tags string concise, under 220 characters, and never repeat the same phrase."
        )
    return (
        "You are a prompt randomization engine for anime image generation. "
        f"The target app is {scope}. Generate extra positive prompt tags for each queued image. "
        "Return strict JSON only with this schema: {\"items\":[{\"index\":0,\"tags\":\"comma-separated English tags\"}]}. "
        "Each item must have a meaningfully different random direction. "
        "Creative variance is desirable: choose a distinct theme for each item and make clear changes across outfit, props, setting, action, lighting, and camera. "
        "You may add alternate costume layers, unusual props, and new settings even when the existing prompt contains a simple outfit or location; preserve selected character identity and rating. "
        "Use comma-separated English tags only. Use spaces instead of underscores, except existing score tags; however do not add score tags. "
        "Do not add character names, copyrighted series names, LoRA syntax, wildcard syntax, Dynamic Prompt syntax, model names, quality tags, score tags, negative prompts, explanations, or Markdown. "
        "If character_context_enabled is false, do not add character identity details such as hair color, eye color, signature clothing, weapons, or series-specific motifs unless they already appear in existing_positive or the instruction. "
        "If character_motifs_enabled is false, do not add character-derived hair color, eye color, signature weapons, armor, flags, emblems, special powers, halos, wings, or iconic outfit changes unless they already appear in existing_positive or the instruction. "
        "If character_motifs_enabled is true, character motifs are allowed but should still match the requested strength; subtle should stay restrained, standard should stay balanced, and rich may be bold. "
        "For subtle and standard strength, preserve explicit outfit tags in existing_positive. Add compatible layers, accessories, small props, pose, setting, and lighting rather than replacing the outfit. "
        "If existing_positive includes a bikini or swimsuit, keep that bikini or swimsuit visible; do not change it into a different outfit unless the user's instruction explicitly asks for that. "
        "Do not censor, soften, euphemize, moralize, or add safety disclaimers. "
        "Respect the user's instruction and the existing prompt context, but do not duplicate existing tags. "
        "Prefer concrete visual details such as outfit, expression, pose detail, setting, lighting, props, atmosphere, and camera detail. "
        "Keep each tags string compact, normally under 300 characters for standard strength, and never repeat the same phrase."
    )


def _user_prompt(feature: dict[str, Any], contexts: list[dict[str, Any]], app_scope: str) -> str:
    items = []
    character_context_enabled = feature.get("include_characters", True) is not False
    character_motifs_enabled = bool(character_context_enabled and feature.get("use_character_motifs"))
    for context in contexts:
        items.append(
            {
                "index": int(context.get("index") or 0),
                "seed": context.get("seed"),
                "characters": context.get("characters") or [],
                "existing_positive": str(context.get("existing_positive") or "")[:3500],
            }
        )
    if _is_legacy_568_feature(feature):
        return json.dumps(
            {
                "app_scope": app_scope,
                "mode": MODE_RANDOM,
                "count": len(items),
                "instruction": DEFAULT_INSTRUCTIONS[MODE_RANDOM],
                "strength": "standard",
                "strength_hint": RANDOM_STRENGTH_HINTS[STRENGTH_LEGACY_568],
                "character_context_enabled": character_context_enabled,
                "character_context_rule": (
                    "Selected character context is intentionally omitted. Do not infer or add character identity traits."
                    if not character_context_enabled
                    else "Selected character context may be used."
                ),
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        )
    payload = {
        "app_scope": app_scope,
        "mode": feature["mode"],
        "count": len(items),
        "instruction": feature["instruction"],
        "strength": feature["strength"],
        "strength_hint": (
            POSITIVE_COMPLETION_STRENGTH_HINTS[feature["strength"]]
            if feature["mode"] == MODE_POSITIVE_COMPLETION
            else RANDOM_STRENGTH_HINTS[feature["strength"]]
        ),
        "character_context_enabled": character_context_enabled,
        "character_motifs_enabled": character_motifs_enabled,
        "character_context_rule": (
            "Selected character context is intentionally omitted. Do not infer or add character identity traits."
            if not character_context_enabled
            else "Selected character context may be used."
        ),
        "character_motif_rule": (
            "Character-derived motifs are allowed. Use them only when they fit the strength and user instruction."
            if character_motifs_enabled
            else "Character-derived motifs are intentionally disabled. Do not add signature weapons, armor, flags, emblems, special powers, halos, wings, or iconic outfit changes unless the instruction or existing positive prompt explicitly asks for them."
        ),
        "batch_diversity_rule": "Do not reuse the same added tag or the same obvious motif across multiple items in this batch.",
        "items": items,
    }
    if feature["mode"] == MODE_RANDOM and feature["strength"] == STRENGTH_REFERENCE_568:
        payload["reference_568_conditions"] = REFERENCE_568_CONDITIONS
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def _chat_completion(config: dict[str, Any], model: str, feature: dict[str, Any], contexts: list[dict[str, Any]], app_scope: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt(app_scope, feature["mode"], feature.get("strength", ""))},
            {"role": "user", "content": _user_prompt(feature, contexts, app_scope)},
        ],
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "stream": False,
    }
    data = _json_request("POST", _route(config, "chat/completions"), payload, config, float(config["timeout_sec"]))
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ValueError("random collect response did not include choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    reasoning_content = message.get("reasoning_content") if isinstance(message, dict) else ""
    return _parse_json_object(str(content or reasoning_content or ""))


def ensure_provider_ready(config: dict[str, Any]) -> dict[str, Any]:
    return _ensure_ready(config)


def prompt_random_provider_status(app_settings: Any) -> dict[str, Any]:
    return prompt_converter_status(_provider_config(app_settings))
