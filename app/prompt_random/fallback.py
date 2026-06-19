from __future__ import annotations

import json
from typing import Any
from urllib import error

from .parser import normalize_prompt_random_collect_items
from .provider import _chat_completion
from .sanitizer import sanitize_generated_random_tags

LOCAL_FALLBACK_TAG_SETS = [
    "soft ambient lighting, atmospheric depth, detailed props, cohesive color palette, natural pose detail",
    "warm window light, layered background detail, relaxed expression, gentle shadows, cozy atmosphere",
    "cinematic framing, subtle motion, textured fabric detail, foreground props, soft depth of field",
    "balanced composition, delicate highlights, environmental storytelling, soft reflections, calm mood",
]
PROMPT_RANDOM_BATCH_ATTEMPTS = 2
PROMPT_RANDOM_SINGLE_ATTEMPTS = 2

def fallback_prompt_random_tags(context: dict[str, Any]) -> str:
    try:
        index = int(context.get("index") or 0)
    except (TypeError, ValueError):
        index = 0
    return LOCAL_FALLBACK_TAG_SETS[index % len(LOCAL_FALLBACK_TAG_SETS)]
def _retryable_exception_message(exc: Exception) -> str:
    return "".join([type(exc).__name__, ": ", str(exc)]).strip()


def _collect_prompt_random_items_once(
    config: dict[str, Any],
    model: str,
    request_config: dict[str, Any],
    contexts: list[dict[str, Any]],
    app_scope: str,
) -> list[dict[str, Any]]:
    data = _chat_completion(config, model, request_config, contexts, app_scope)
    return normalize_prompt_random_collect_items(data, contexts)


def _collect_prompt_random_items_with_fallback(
    config: dict[str, Any],
    model: str,
    request_config: dict[str, Any],
    contexts: list[dict[str, Any]],
    app_scope: str,
    *,
    collect_once: Any | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    errors: list[str] = []
    collect_once = collect_once or _collect_prompt_random_items_once
    for attempt in range(1, PROMPT_RANDOM_BATCH_ATTEMPTS + 1):
        try:
            items = collect_once(config, model, request_config, contexts, app_scope)
            return items, {"mode": "batch", "batch_attempts": attempt, "fallback": False, "errors": errors}
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"batch attempt {attempt}: {_retryable_exception_message(exc)}")

    generated_items: list[dict[str, Any]] = []
    single_attempts = 0
    for context in contexts:
        single_context = [context]
        for attempt in range(1, PROMPT_RANDOM_SINGLE_ATTEMPTS + 1):
            single_attempts += 1
            try:
                generated_items.extend(collect_once(config, model, request_config, single_context, app_scope))
                break
            except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"single index {context.get('index')} attempt {attempt}: {_retryable_exception_message(exc)}")
        else:
            generated_items.append({"index": int(context.get("index") or 0), "seed": context.get("seed"), "tags": sanitize_generated_random_tags("", context)})
            errors.append(f"single index {context.get('index')}: used local fallback tags")

    return generated_items, {
        "mode": "single_fallback",
        "batch_attempts": PROMPT_RANDOM_BATCH_ATTEMPTS,
        "single_attempts": single_attempts,
        "fallback": True,
        "errors": errors[-6:],
    }
