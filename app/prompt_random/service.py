from __future__ import annotations

import json
from typing import Any
from urllib import error

from ..prompt_converter import prompt_converter_status
from ..schemas.generation import PromptRandomCollectSettings
from .fallback import _collect_prompt_random_items_with_fallback
from .provider import _provider_config, ensure_provider_ready
from .settings import DEFAULT_INSTRUCTION, MODE_RANDOM

def sanitize_prompt_random_collect_request(value: Any) -> dict[str, Any]:
    raw = value.model_dump() if hasattr(value, "model_dump") else value if isinstance(value, dict) else {}
    return PromptRandomCollectSettings.model_validate(raw).model_dump()


def prompt_random_collect_enabled(value: Any) -> bool:
    return bool(sanitize_prompt_random_collect_request(value).get("enabled"))


def prompt_random_collect_status(app_settings: Any) -> dict[str, Any]:
    config = _provider_config(app_settings)
    status = prompt_converter_status(config)
    return {"feature": "prompt_random_collect", **status}

def collect_prompt_random_tags(
    app_settings: Any,
    *,
    feature: Any,
    contexts: list[dict[str, Any]],
    app_scope: str,
    collect_with_fallback: Any | None = None,
    provider_config: Any | None = None,
    ensure_ready: Any | None = None,
) -> dict[str, Any]:
    request_config = sanitize_prompt_random_collect_request(feature)
    if not request_config["enabled"]:
        return {"ok": True, "enabled": False, "generated_items": []}
    if not contexts:
        return {"ok": False, "status": 400, "stage": "prompt_random_collect_context", "message": "Random Collect context is empty."}
    contexts = [
        {
            **context,
            "prompt_random_collect_mode": request_config["mode"],
            "prompt_random_collect_strength": request_config["strength"],
            "prompt_random_collect_instruction": request_config["instruction"],
            "prompt_random_collect_use_character_motifs": bool(
                request_config["include_characters"] and request_config["use_character_motifs"]
            ),
        }
        for context in contexts
    ]

    provider_config = provider_config or _provider_config
    ensure_ready = ensure_ready or ensure_provider_ready
    config = provider_config(app_settings, request_config)
    if not config["enabled"]:
        return {"ok": False, "status": 400, "stage": "prompt_random_collect_disabled", "message": "Prompt Random Collect provider is disabled."}
    status = ensure_ready(config)
    if not status.get("reachable"):
        return {"ok": False, "status": 502, "stage": "prompt_random_collect_provider", "message": status.get("message") or "Local prompt random collect API is not reachable.", "provider_status": status}
    models = status.get("models") if isinstance(status.get("models"), list) else []
    model = str(config.get("model") or "auto")
    if model == "auto":
        model = str(models[0] if models else "")
    if not model:
        return {"ok": False, "status": 502, "stage": "prompt_random_collect_model", "message": "Prompt random collect model is not loaded.", "provider_status": status}

    try:
        collector = collect_with_fallback or _collect_prompt_random_items_with_fallback
        generated_items, generation_strategy = collector(config, model, request_config, contexts, app_scope)
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": 502, "stage": "prompt_random_collect_generate", "message": str(exc), "provider_status": status}

    return {
        "ok": True,
        "enabled": True,
        "mode": request_config["mode"],
        "instruction": request_config["instruction"],
        "strength": request_config["strength"],
        "include_characters": request_config["include_characters"],
        "use_character_motifs": bool(request_config["include_characters"] and request_config["use_character_motifs"]),
        "generated_items": generated_items,
        "generation_strategy": generation_strategy,
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
            "use_character_motifs": bool(
                result.get("include_characters", current.get("include_characters", True)) is not False
                and result.get("use_character_motifs", current.get("use_character_motifs", True))
            ),
            "generated_item": generated_item,
            "generated_tags": generated_item.get("tags", "") if isinstance(generated_item, dict) else "",
            "provider": result.get("provider") or {},
            "generation_strategy": result.get("generation_strategy") or {},
        }


def prompt_random_collect_tags(request_data: dict[str, Any]) -> str:
    data = request_data.get("prompt_random_collect") if isinstance(request_data, dict) else None
    if not isinstance(data, dict) or not data.get("enabled"):
        return ""
    generated_item = data.get("generated_item") if isinstance(data.get("generated_item"), dict) else {}
    return str(generated_item.get("tags") or data.get("generated_tags") or "").strip()
