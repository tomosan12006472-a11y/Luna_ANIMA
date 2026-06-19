from __future__ import annotations

from typing import Any, Callable


def prompt_random_collect_context_request(request_data: dict[str, Any], *, include_characters: bool) -> dict[str, Any]:
    if include_characters:
        return request_data
    context_request = dict(request_data)
    context_request.update(
        {
            "character1": "None",
            "character2": "None",
            "character3": "None",
            "original_character": "None",
        }
    )
    return context_request


def build_prompt_random_collect_contexts(
    request_data_items: list[dict[str, Any]],
    *,
    include_characters: bool,
    build_prompts_func: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for position, request_data in enumerate(request_data_items):
        context_request = prompt_random_collect_context_request(request_data, include_characters=include_characters)
        prompts = build_prompts_func(context_request)
        contexts.append(
            {
                "index": int(request_data.get("queue_index") or position),
                "seed": prompts.get("seed", request_data.get("seed")),
                "characters": prompts.get("characters", []) if include_characters else [],
                "character_metadata": prompts.get("character_metadata", []) if include_characters else [],
                "existing_positive": prompts.get("positive", ""),
                "suppress_character_identity": not include_characters,
            }
        )
    return contexts
