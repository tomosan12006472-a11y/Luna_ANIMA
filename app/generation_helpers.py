from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse

from . import comfy_client
from .history_store import list_all_history_with_warnings
from .payload_builder import build_prompts
from .prompt_random.context import build_prompt_random_collect_contexts, prompt_random_collect_context_request
from .prompt_random_collect import (
    attach_prompt_random_collect_items,
    collect_prompt_random_tags,
    prompt_random_collect_enabled,
    sanitize_prompt_random_collect_request,
)
from .schemas.generation import GenerateRequest
from .settings_store import load_app_settings
from .validators import error_response


@dataclass
class ComfyCacheResetResult:
    requested: bool = False
    eligible: bool = False
    applied: bool = False
    skipped: bool = False
    reason: str = ""
    status: int | None = None
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested": bool(self.requested),
            "eligible": bool(self.eligible),
            "applied": bool(self.applied),
            "skipped": bool(self.skipped),
            "reason": str(self.reason or ""),
            "status": self.status,
            "error": str(self.error or ""),
        }


def _has_fixed_character_selection(data: Any) -> bool:
    def selected(value: Any) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized not in {"", "none", "random"}

    return any(
        selected(getattr(data, field, ""))
        for field in ("character1", "character2", "character3", "original_character")
    )


def prepare_comfy_cache_reset_for_character_prompt(addr: str, data: GenerateRequest) -> tuple[JSONResponse | None, dict[str, Any]]:
    result = ComfyCacheResetResult(requested=bool(data.reset_comfy_cache))
    if not result.requested:
        return None, result.as_dict()
    if not _has_fixed_character_selection(data):
        result.skipped = True
        result.reason = "no_fixed_character"
        return None, result.as_dict()
    try:
        queue = comfy_client.queue_info(addr)
    except Exception as exc:
        result.reason = "queue_check_failed"
        result.error = str(exc)
        return error_response(
            status_code=502,
            message="Failed to inspect ComfyUI queue before cache reset.",
            stage="comfy_cache_reset_queue_check",
            data=data,
            comfy_response_text=str(exc),
            retryable=True,
            extra={"comfy_cache_reset": result.as_dict()},
        ), result.as_dict()
    result.eligible = True
    if queue.get("queue_running") or queue.get("queue_pending"):
        result.reason = "queue_not_empty"
        return error_response(
            status_code=409,
            message="ComfyUI cache reset was skipped because the queue is not empty.",
            stage="comfy_cache_reset_queue_check",
            data=data,
            retryable=True,
            extra={"comfy_cache_reset": result.as_dict()},
        ), result.as_dict()
    reset_result = comfy_client.reset_execution_cache(addr)
    result.status = reset_result.get("status")
    if reset_result.get("ok"):
        result.applied = True
        return None, result.as_dict()
    result.reason = "reset_failed"
    result.error = str(reset_result.get("text") or "")
    return error_response(
        status_code=502,
        message="Failed to reset ComfyUI execution cache before character generation.",
        stage="comfy_cache_reset",
        data=data,
        comfy_status=reset_result.get("status"),
        comfy_response_text=str(reset_result.get("text") or ""),
        retryable=True,
        extra={"comfy_cache_reset": result.as_dict()},
    ), result.as_dict()


def reset_comfy_cache_for_character_prompt(addr: str, data: GenerateRequest) -> JSONResponse | None:
    error, _metadata = prepare_comfy_cache_reset_for_character_prompt(addr, data)
    return error


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


def apply_prompt_random_collect_or_error(request_data_items: list[dict[str, Any]]) -> JSONResponse | None:
    if not request_data_items:
        return None
    feature = request_data_items[0].get("prompt_random_collect")
    feature_config = sanitize_prompt_random_collect_request(feature)
    if not prompt_random_collect_enabled(feature_config):
        return None
    include_characters = bool(feature_config.get("include_characters", True))
    contexts = build_prompt_random_collect_contexts(
        request_data_items,
        include_characters=include_characters,
        build_prompts_func=build_prompts,
    )
    result = collect_prompt_random_tags(load_app_settings(), feature=feature_config, contexts=contexts, app_scope="anima")
    if not result.get("ok"):
        return prompt_random_collect_error_response(result)
    attach_prompt_random_collect_items(request_data_items, result)
    return None
