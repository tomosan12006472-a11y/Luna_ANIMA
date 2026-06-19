from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from . import comfy_client
from .history_store import list_all_history_with_warnings
from .payload_builder import build_prompts
from .prompt_random_collect import (
    attach_prompt_random_collect_items,
    collect_prompt_random_tags,
    prompt_random_collect_enabled,
    sanitize_prompt_random_collect_request,
)
from .schemas.generation import GenerateRequest
from .settings_store import load_app_settings
from .validators import error_response


def _has_fixed_character_selection(data: Any) -> bool:
    def selected(value: Any) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized not in {"", "none", "random"}

    return any(
        selected(getattr(data, field, ""))
        for field in ("character1", "character2", "character3", "original_character")
    )


def reset_comfy_cache_for_character_prompt(addr: str, data: GenerateRequest) -> JSONResponse | None:
    if not data.reset_comfy_cache:
        return None
    if not _has_fixed_character_selection(data):
        return None
    try:
        queue = comfy_client.queue_info(addr)
    except Exception as exc:
        return error_response(
            status_code=502,
            message="Failed to inspect ComfyUI queue before cache reset.",
            stage="comfy_cache_reset_queue_check",
            data=data,
            comfy_response_text=str(exc),
            retryable=True,
        )
    if queue.get("queue_running") or queue.get("queue_pending"):
        return error_response(
            status_code=409,
            message="ComfyUI cache reset was skipped because the queue is not empty.",
            stage="comfy_cache_reset_queue_check",
            data=data,
            retryable=True,
        )
    result = comfy_client.reset_execution_cache(addr)
    if result.get("ok"):
        return None
    return error_response(
        status_code=502,
        message="Failed to reset ComfyUI execution cache before character generation.",
        stage="comfy_cache_reset",
        data=data,
        comfy_status=result.get("status"),
        comfy_response_text=str(result.get("text") or ""),
        retryable=True,
    )


def pending_history_by_prompt_id() -> dict[str, dict[str, Any]]:
    items, _warnings = list_all_history_with_warnings()
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        status = str(item.get("status") or "")
        prompt_id = str(item.get("prompt_id") or "")
        if status in {"queued", "running"} and prompt_id:
            result[prompt_id] = item
    return result


def _looks_like_prompt_id(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) < 8:
        return False
    return "-" in text or all(char in "0123456789abcdefABCDEF" for char in text)


def _queue_entry_prompt_id(entry: Any) -> str:
    if isinstance(entry, dict):
        for key in ("prompt_id", "id"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                return value
    if isinstance(entry, (list, tuple)):
        for index in (1, 0):
            if index < len(entry) and isinstance(entry[index], str) and _looks_like_prompt_id(entry[index]):
                return entry[index]
        for value in entry:
            prompt_id = _queue_entry_prompt_id(value)
            if prompt_id:
                return prompt_id
    return ""


def queue_rows(entries: Any, history_by_prompt_id: dict[str, dict[str, Any]], *, include_position: bool) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        prompt_id = _queue_entry_prompt_id(entry)
        history_item = history_by_prompt_id.get(prompt_id)
        row: dict[str, Any] = {
            "prompt_id": prompt_id,
            "ours": bool(history_item),
        }
        if include_position:
            row["position"] = index + 1
        if history_item:
            row["history_id"] = history_item.get("id") or history_item.get("history_id")
        rows.append(row)
    return rows


def prompt_random_collect_error_response(result: dict[str, Any]) -> JSONResponse:
    status_code = int(result.get("status") or 502)
    return JSONResponse(status_code=status_code, content=result)


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


def apply_prompt_random_collect_or_error(request_data_items: list[dict[str, Any]]) -> JSONResponse | None:
    if not request_data_items:
        return None
    feature = request_data_items[0].get("prompt_random_collect")
    feature_config = sanitize_prompt_random_collect_request(feature)
    if not prompt_random_collect_enabled(feature_config):
        return None
    include_characters = bool(feature_config.get("include_characters", True))
    contexts: list[dict[str, Any]] = []
    for position, request_data in enumerate(request_data_items):
        context_request = prompt_random_collect_context_request(request_data, include_characters=include_characters)
        prompts = build_prompts(context_request)
        contexts.append(
            {
                "index": int(request_data.get("queue_index") or position),
                "seed": prompts.get("seed", request_data.get("seed")),
                "characters": prompts.get("characters", []) if include_characters else [],
                "existing_positive": prompts.get("positive", ""),
                "suppress_character_identity": not include_characters,
            }
        )
    result = collect_prompt_random_tags(load_app_settings(), feature=feature_config, contexts=contexts, app_scope="anima")
    if not result.get("ok"):
        return prompt_random_collect_error_response(result)
    attach_prompt_random_collect_items(request_data_items, result)
    return None
