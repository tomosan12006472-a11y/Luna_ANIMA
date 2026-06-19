from __future__ import annotations

import json
import re
from typing import Any
from urllib import error

from .prompt_converter import (
    SCORE_TAG_RE,
    _deep_merge,
    _ensure_ready,
    _json_request,
    _parse_json_object,
    _route,
    normalize_tag_prompt,
    prompt_converter_status,
    sanitize_prompt_converter_settings,
    split_prompt_tags,
)
from .prompt_random.context import build_prompt_random_collect_contexts, prompt_random_collect_context_request
from .prompt_random.fallback import (
    LOCAL_FALLBACK_TAG_SETS,
    PROMPT_RANDOM_BATCH_ATTEMPTS,
    PROMPT_RANDOM_SINGLE_ATTEMPTS,
    fallback_prompt_random_tags,
)
from .prompt_random import fallback as _fallback
from .prompt_random import service as _service
from .prompt_random.parser import _raw_item_tags, normalize_prompt_random_collect_items
from .prompt_random.provider import _legacy_568_system_prompt, _provider_config, _system_prompt, _user_prompt
from .prompt_random.sanitizer import (
    _character_motif_override_requested,
    _character_reference_keys,
    _identity_terms,
    _random_tag_key,
    clamp_prompt_random_tags,
    filter_character_motif_tags,
    filter_character_reference_tags,
    filter_disallowed_random_tags,
    filter_heavy_random_motif_tags,
    filter_outfit_replacement_tags,
    filter_reference_568_identity_overrides,
    prompt_random_limits,
    sanitize_generated_random_tags,
    strip_character_identity_tags,
)
from .prompt_random.service import (
    attach_prompt_random_collect_items,
    prompt_random_collect_enabled,
    prompt_random_collect_status,
    prompt_random_collect_tags,
    sanitize_prompt_random_collect_request,
)
from .prompt_random.settings import (
    CHARACTER_IDENTITY_RE,
    CHARACTER_IDENTITY_TERMS,
    CHARACTER_MOTIF_OVERRIDE_RE,
    CHARACTER_MOTIF_RE,
    CHARACTER_MOTIF_TERMS,
    DEFAULT_INSTRUCTION,
    DEFAULT_INSTRUCTIONS,
    DISALLOWED_RANDOM_TAG_KEYS,
    DISALLOWED_RANDOM_TAG_RE,
    HAIR_EYE_COLOR_RE,
    HEAVY_RANDOM_MOTIF_RE,
    LIGHT_PROP_WEAPON_RE,
    MAX_LEGACY_568_RANDOM_TAG_CHARS,
    MAX_LEGACY_568_RANDOM_TAGS,
    MAX_POSITIVE_COMPLETION_TAG_CHARS,
    MAX_POSITIVE_COMPLETION_TAGS,
    MAX_RANDOM_TAG_CHARS,
    MAX_RANDOM_TAG_LIMITS_BY_STRENGTH,
    MAX_RANDOM_TAGS,
    MODE_POSITIVE_COMPLETION,
    MODE_RANDOM,
    POSITIVE_COMPLETION_STRENGTH_HINTS,
    RANDOM_STRENGTH_HINTS,
    REFERENCE_568_CONDITIONS,
    SMALL_PROP_RE,
    STRENGTH_LEGACY_568,
    STRENGTH_REFERENCE_568,
    SWIMWEAR_RE,
    VALID_MODES,
    VALID_STRENGTHS,
    _clamp_text,
    _is_legacy_568_context,
    _is_legacy_568_feature,
)
from .schemas.generation import PromptRandomCollectSettings


def _chat_completion(config, model, feature, contexts, app_scope):
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


def _collect_prompt_random_items_once(config, model, request_config, contexts, app_scope):
    data = _chat_completion(config, model, request_config, contexts, app_scope)
    return normalize_prompt_random_collect_items(data, contexts)


def _collect_prompt_random_items_with_fallback(config, model, request_config, contexts, app_scope):
    return _fallback._collect_prompt_random_items_with_fallback(
        config,
        model,
        request_config,
        contexts,
        app_scope,
        collect_once=_collect_prompt_random_items_once,
    )


def _retryable_exception_message(exc):
    return _fallback._retryable_exception_message(exc)


def prompt_random_collect_status(app_settings):
    config = _provider_config(app_settings)
    status = prompt_converter_status(config)
    return {"feature": "prompt_random_collect", **status}


def collect_prompt_random_tags(app_settings, *, feature, contexts, app_scope):
    return _service.collect_prompt_random_tags(
        app_settings,
        feature=feature,
        contexts=contexts,
        app_scope=app_scope,
        collect_with_fallback=_collect_prompt_random_items_with_fallback,
        provider_config=_provider_config,
        ensure_ready=lambda config: _ensure_ready(config),
    )
