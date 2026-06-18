from __future__ import annotations

import json
import re
from typing import Any
from urllib import error

from .prompt_converter import (
    _deep_merge,
    _ensure_ready,
    _json_request,
    _parse_json_object,
    _route,
    normalize_tag_prompt,
    prompt_converter_status,
    sanitize_prompt_converter_settings,
)


MODE_RANDOM = "random"
MODE_POSITIVE_COMPLETION = "positive_completion"
VALID_MODES = {MODE_RANDOM, MODE_POSITIVE_COMPLETION}
DEFAULT_INSTRUCTIONS = {
    MODE_RANDOM: "衣装、表情、背景、小物をランダムに足す",
    MODE_POSITIVE_COMPLETION: "既存Positiveの意図を保ったまま、不足している描写を英語タグで補う",
}
DEFAULT_INSTRUCTION = DEFAULT_INSTRUCTIONS[MODE_RANDOM]
VALID_STRENGTHS = {"subtle", "standard", "rich"}
STRENGTH_HINTS = {
    "subtle": "Add 2 to 4 concise visual tags per item.",
    "standard": "Add 5 to 8 concise visual tags per item.",
    "rich": "Add 8 to 12 vivid visual tags per item without bloating the prompt.",
}


def _clamp_text(value: Any, default: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        text = default
    return text[:limit]


def sanitize_prompt_random_collect_request(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    mode = str(raw.get("mode") or MODE_RANDOM).strip().lower()
    if mode not in VALID_MODES:
        mode = MODE_RANDOM
    strength = str(raw.get("strength") or "standard").strip().lower()
    if strength not in VALID_STRENGTHS:
        strength = "standard"
    include_characters = raw.get("include_characters", True)
    if isinstance(include_characters, str):
        include_characters = include_characters.strip().lower() not in {"0", "false", "off", "no"}
    else:
        include_characters = bool(include_characters)
    return {
        "enabled": bool(raw.get("enabled")),
        "mode": mode,
        "instruction": _clamp_text(raw.get("instruction"), DEFAULT_INSTRUCTIONS[mode], 1000),
        "strength": strength,
        "include_characters": include_characters,
    }


def prompt_random_collect_enabled(value: Any) -> bool:
    return bool(sanitize_prompt_random_collect_request(value).get("enabled"))


def _provider_config(app_settings: Any, feature: Any = None) -> dict[str, Any]:
    settings = app_settings if isinstance(app_settings, dict) else {}
    base = settings.get("prompt_converter") if isinstance(settings.get("prompt_converter"), dict) else {}
    override = settings.get("prompt_random_collect_provider") if isinstance(settings.get("prompt_random_collect_provider"), dict) else {}
    config = sanitize_prompt_converter_settings(_deep_merge(base, override))
    mode = sanitize_prompt_random_collect_request(feature).get("mode") if feature is not None else MODE_RANDOM
    min_temperature = 0.35 if mode == MODE_POSITIVE_COMPLETION else 0.85
    config["temperature"] = max(float(config.get("temperature") or 0.0), min_temperature)
    config["max_tokens"] = max(int(config.get("max_tokens") or 0), 1800)
    return config


def prompt_random_collect_status(app_settings: Any) -> dict[str, Any]:
    config = _provider_config(app_settings)
    status = prompt_converter_status(config)
    return {"feature": "prompt_random_collect", **status}


def _system_prompt(app_scope: str, mode: str) -> str:
    scope = "Luna ANIMA" if app_scope == "anima" else "Luna SDXL"
    if mode == MODE_POSITIVE_COMPLETION:
        return (
            "You are a positive prompt completion engine for anime image generation. "
            f"The target app is {scope}. Generate only additional positive prompt tags that complete and polish each existing prompt. "
            "Return strict JSON only with this schema: {\"items\":[{\"index\":0,\"tags\":\"comma-separated English tags\"}]}. "
            "Use comma-separated English tags only. Use spaces instead of underscores, except existing score tags; however do not add score tags. "
            "Do not rewrite or repeat the existing prompt. Add only missing, useful, concrete tags that fit the current context. "
            "Do not contradict selected characters, setting, rating, camera, lighting, outfit, pose, or user wording. "
            "Do not add character names, copyrighted series names, LoRA syntax, wildcard syntax, Dynamic Prompt syntax, model names, quality tags, score tags, negative prompts, explanations, or Markdown. "
            "Do not censor, soften, euphemize, moralize, or add safety disclaimers. "
            "Prefer coherent visual details such as expression nuance, pose detail, material, setting detail, lighting, props, atmosphere, composition, and camera detail."
        )
    return (
        "You are a prompt randomization engine for anime image generation. "
        f"The target app is {scope}. Generate extra positive prompt tags for each queued image. "
        "Return strict JSON only with this schema: {\"items\":[{\"index\":0,\"tags\":\"comma-separated English tags\"}]}. "
        "Each item must have a meaningfully different random direction. "
        "Use comma-separated English tags only. Use spaces instead of underscores, except existing score tags; however do not add score tags. "
        "Do not add character names, copyrighted series names, LoRA syntax, wildcard syntax, Dynamic Prompt syntax, model names, quality tags, score tags, negative prompts, explanations, or Markdown. "
        "Do not censor, soften, euphemize, moralize, or add safety disclaimers. "
        "Respect the user's instruction and the existing prompt context, but do not duplicate existing tags. "
        "Prefer concrete visual details such as outfit, expression, pose detail, setting, lighting, props, atmosphere, and camera detail."
    )


def _user_prompt(feature: dict[str, Any], contexts: list[dict[str, Any]], app_scope: str) -> str:
    items = []
    for context in contexts:
        items.append(
            {
                "index": int(context.get("index") or 0),
                "seed": context.get("seed"),
                "characters": context.get("characters") or [],
                "existing_positive": str(context.get("existing_positive") or "")[:3500],
            }
        )
    return json.dumps(
        {
            "app_scope": app_scope,
            "mode": feature["mode"],
            "count": len(items),
            "instruction": feature["instruction"],
            "strength": feature["strength"],
            "strength_hint": STRENGTH_HINTS[feature["strength"]],
            "items": items,
        },
        ensure_ascii=False,
        indent=2,
    )


def _chat_completion(config: dict[str, Any], model: str, feature: dict[str, Any], contexts: list[dict[str, Any]], app_scope: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt(app_scope, feature["mode"])},
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


def _raw_item_tags(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("tags") or item.get("tags_en") or item.get("prompt") or item.get("text") or "").strip()
    return str(item or "").strip()


def normalize_prompt_random_collect_items(data: dict[str, Any], contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        raise ValueError("random collect response must include an items array")
    if len(raw_items) < len(contexts):
        raise ValueError(f"random collect returned {len(raw_items)} items for {len(contexts)} queued images")

    by_index: dict[int, Any] = {}
    ordered: list[Any] = []
    for position, raw in enumerate(raw_items):
        raw_index = raw.get("index") if isinstance(raw, dict) else None
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            index = position
        by_index[index] = raw
        ordered.append(raw)

    generated: list[dict[str, Any]] = []
    seen_tags: set[str] = set()
    for position, context in enumerate(contexts):
        index = int(context.get("index") or position)
        raw = by_index.get(index, ordered[position] if position < len(ordered) else {})
        tags = normalize_tag_prompt(_raw_item_tags(raw), context.get("existing_positive", ""))
        tags = re.sub(r"\s+", " ", tags).strip(" ,")
        if not tags:
            raise ValueError(f"random collect item {index} did not include usable tags")
        key = tags.lower()
        if len(contexts) > 1 and key in seen_tags:
            raise ValueError("random collect returned duplicate tag sets")
        seen_tags.add(key)
        generated.append({"index": index, "seed": context.get("seed"), "tags": tags})
    return generated


def collect_prompt_random_tags(
    app_settings: Any,
    *,
    feature: Any,
    contexts: list[dict[str, Any]],
    app_scope: str,
) -> dict[str, Any]:
    request_config = sanitize_prompt_random_collect_request(feature)
    if not request_config["enabled"]:
        return {"ok": True, "enabled": False, "generated_items": []}
    if not contexts:
        return {"ok": False, "status": 400, "stage": "prompt_random_collect_context", "message": "Random Collect context is empty."}

    config = _provider_config(app_settings, request_config)
    if not config["enabled"]:
        return {"ok": False, "status": 400, "stage": "prompt_random_collect_disabled", "message": "Prompt Random Collect provider is disabled."}
    status = _ensure_ready(config)
    if not status.get("reachable"):
        return {"ok": False, "status": 502, "stage": "prompt_random_collect_provider", "message": status.get("message") or "Local prompt random collect API is not reachable.", "provider_status": status}
    models = status.get("models") if isinstance(status.get("models"), list) else []
    model = str(config.get("model") or "auto")
    if model == "auto":
        model = str(models[0] if models else "")
    if not model:
        return {"ok": False, "status": 502, "stage": "prompt_random_collect_model", "message": "Prompt random collect model is not loaded.", "provider_status": status}

    try:
        data = _chat_completion(config, model, request_config, contexts, app_scope)
        generated_items = normalize_prompt_random_collect_items(data, contexts)
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": 502, "stage": "prompt_random_collect_generate", "message": str(exc), "provider_status": status}

    return {
        "ok": True,
        "enabled": True,
        "mode": request_config["mode"],
        "instruction": request_config["instruction"],
        "strength": request_config["strength"],
        "include_characters": request_config["include_characters"],
        "generated_items": generated_items,
        "provider": {
            "provider": config["provider"],
            "base_url": config["base_url"],
            "model": model,
        },
    }


def attach_prompt_random_collect_items(request_data_items: list[dict[str, Any]], result: dict[str, Any]) -> None:
    generated_items = result.get("generated_items") if isinstance(result.get("generated_items"), list) else []
    by_index = {int(item.get("index") or position): item for position, item in enumerate(generated_items) if isinstance(item, dict)}
    for position, request_data in enumerate(request_data_items):
        queue_index = int(request_data.get("queue_index") or position)
        generated_item = by_index.get(queue_index, generated_items[position] if position < len(generated_items) else {})
        current = request_data.get("prompt_random_collect") if isinstance(request_data.get("prompt_random_collect"), dict) else {}
        request_data["prompt_random_collect"] = {
            "enabled": True,
            "mode": result.get("mode") or current.get("mode") or MODE_RANDOM,
            "instruction": result.get("instruction") or current.get("instruction") or DEFAULT_INSTRUCTION,
            "strength": result.get("strength") or current.get("strength") or "standard",
            "include_characters": result.get("include_characters", current.get("include_characters", True)) is not False,
            "generated_item": generated_item,
            "generated_tags": generated_item.get("tags", "") if isinstance(generated_item, dict) else "",
            "provider": result.get("provider") or {},
        }


def prompt_random_collect_tags(request_data: dict[str, Any]) -> str:
    data = request_data.get("prompt_random_collect") if isinstance(request_data, dict) else None
    if not isinstance(data, dict) or not data.get("enabled"):
        return ""
    generated_item = data.get("generated_item") if isinstance(data.get("generated_item"), dict) else {}
    return str(generated_item.get("tags") or data.get("generated_tags") or "").strip()
