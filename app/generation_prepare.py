from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import secrets
import traceback
from typing import Any
import uuid

from . import comfy_client
from . import i2i_store
from . import lora_catalog
from . import reference_store
from .config import MOBILE_PAYLOAD_DIR
from .face_detailer import face_detailer_capabilities
from .face_detailer import sanitize_face_detailer_settings
from .face_detailer import sanitize_hand_detailer_settings
from .history_flags_store import attach_flags_to_items, filter_items_by_flags, flag_summary
from .history_store import (
    complete_pending_history_item,
    create_history_item,
    is_pending_item,
    list_all_history_with_warnings,
    pending_age_is_missing,
    pending_age_is_stale,
    summarize_history,
    update_pending_history_status,
)
from .history_search import search_history_items
from .model_info_cache import cached_object_info
from .payload_builder import model_sampling_shift_metadata
from .reference_modules import reference_module_capabilities, reference_module_model_status, sanitize_reference_modules


def reference_capability_payload(addr: str, refresh: bool = False) -> dict[str, Any]:
    try:
        info, cache = cached_object_info(addr, refresh=refresh)
    except Exception as exc:
        return {
            "ok": False,
            "reference_assist": {
                "supported": False,
                "preferred_mode": None,
                "modes": {},
                "controlnet_models": [],
                "upload_supported": False,
                "notes": [str(exc)],
            },
        }
    return {"ok": True, **reference_store.reference_capabilities(info, cache=cache)}


def reference_modules_availability_payload(addr: str, refresh: bool = False) -> dict[str, Any]:
    try:
        info, cache = cached_object_info(addr, refresh=refresh)
    except Exception as exc:
        return {
            "ok": False,
            "reference_modules": {
                "outfit": {
                    "implemented": True,
                    "available": False,
                    "strategy": "ip_adapter",
                    "warnings": [str(exc)],
                },
                "pose": {
                    "implemented": True,
                    "available": False,
                    "strategy": "controlnet_openpose",
                    "warnings": [str(exc)],
                },
                "background": {
                    "implemented": True,
                    "available": False,
                    "strategy": "controlnet_background",
                    "warnings": [str(exc)],
                },
            },
        }
    return {"ok": True, **reference_module_capabilities(info, cache=cache, app_scope="anima")}


def reference_modules_model_status_payload(addr: str, refresh: bool = False) -> dict[str, Any]:
    comfy_roots = [Path(r"D:\AI\ComfyUI\ComfyUI"), Path(r"D:\AI\ComfyUI")]
    try:
        info, cache = cached_object_info(addr, refresh=refresh)
    except Exception as exc:
        return {
            "ok": False,
            "comfyui": {"reachable": False, "object_info_checked": False, "error": str(exc)},
            "modules": reference_module_model_status({}, comfyui_roots=comfy_roots, app_scope="anima").get("modules", {}),
        }
    status = reference_module_model_status(info, comfyui_roots=comfy_roots, app_scope="anima")
    status["comfyui"] = {"reachable": True, "object_info_checked": True, "cache": cache}
    return status


def i2i_capability_payload(addr: str, refresh: bool = False) -> dict[str, Any]:
    try:
        info, cache = cached_object_info(addr, refresh=refresh)
    except Exception as exc:
        return {"ok": False, "image_to_image": {"supported": False, "warnings": [str(exc)]}}
    return {"ok": True, **i2i_store.i2i_capabilities(info, cache=cache)}


def face_detailer_capability_payload(addr: str, refresh: bool = False) -> dict[str, Any]:
    try:
        info, cache = cached_object_info(addr, refresh=refresh)
    except Exception as exc:
        return {"ok": False, "face_detailer": {"supported": False, "warnings": [str(exc)]}}
    return {"ok": True, "face_detailer": face_detailer_capabilities(info), "cache": cache}


def generation_request_dict(data: Any) -> dict[str, Any]:
    request_data = data.model_dump()
    dynamic_prompt = request_data.get("dynamic_prompt") if isinstance(request_data.get("dynamic_prompt"), dict) else {}
    if dynamic_prompt.get("wildcard_seed") is None:
        dynamic_prompt.pop("wildcard_seed", None)
        request_data["dynamic_prompt"] = dynamic_prompt
    request_data["loras"] = lora_catalog.normalize_lora_slots(request_data.get("loras"))
    request_data["model_sampling"] = model_sampling_shift_metadata(request_data)
    request_data["shift"] = request_data["model_sampling"].get("shift")
    request_data["reference_assist"] = reference_store.sanitize_reference_assist(
        request_data.get("reference_assist"),
        app_scope="anima",
        default_strength=0.25,
    )
    request_data["reference_modules"] = sanitize_reference_modules(request_data.get("reference_modules"), app_scope="anima")
    request_data["image_to_image"] = i2i_store.sanitize_image_to_image(request_data.get("image_to_image"), app_scope="anima")
    request_data["face_detailer"] = sanitize_face_detailer_settings(request_data.get("face_detailer"), mode="generation")
    request_data["hand_detailer"] = sanitize_hand_detailer_settings(request_data.get("hand_detailer"), mode="generation")
    return request_data


def write_mobile_payload_dump(payload: dict[str, Any], request_data: dict[str, Any], generation_mode: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"mobile_{timestamp}_{uuid.uuid4().hex[:8]}.json"
    path = MOBILE_PAYLOAD_DIR / name
    data = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "generation_mode": generation_mode,
        "request": request_data,
        "payload": payload,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_mobile_payload(payload: dict[str, Any], request: Any) -> Path:
    return write_mobile_payload_dump(payload, request.model_dump(), request.workflow_mode)


def save_mobile_payload_data(payload: dict[str, Any], request_data: dict[str, Any], generation_mode: str) -> Path:
    return write_mobile_payload_dump(payload, request_data, generation_mode)


def seed_for_index(data: Any, index: int) -> int:
    if data.seed_mode == "fixed" and data.seed >= 0:
        return data.seed + index
    return secrets.randbelow(4294967296)


def request_for_queue_item(data: Any, index: int, wait: bool) -> Any:
    return data.model_copy(update={"seed": seed_for_index(data, index), "count": 1, "wait": wait})


def save_completed_generation_history(
    *,
    addr: str,
    request_data: dict[str, Any],
    prompts: dict[str, Any],
    prompt_id: str,
    payload_path: str,
    workflow_mode: str,
    history_id: str | None = None,
) -> None:
    try:
        history = comfy_client.wait_history(addr, prompt_id, timeout=3600)
        if not history:
            print(f"[anima-mobile] prompt {prompt_id} did not finish before background history timeout")
            if history_id:
                queue_status = None
                try:
                    queue_status = comfy_client.queued_prompt_status(comfy_client.queue_info(addr), prompt_id)
                except Exception:
                    queue_status = None
                if queue_status:
                    update_pending_history_status(history_id, queue_status)
                else:
                    update_pending_history_status(history_id, "stale", "Timed out waiting for ComfyUI history")
            return
        image = comfy_client.first_output_image(history)
        if not image:
            print(f"[anima-mobile] prompt {prompt_id} finished without output image")
            if history_id:
                update_pending_history_status(history_id, "failed", comfy_client.history_status_message(history))
            return
        image_url, image_data_url = comfy_client.fetch_image_data_url(addr, image)
        result = comfy_client.ComfyResult(
            ok=True,
            prompt_id=prompt_id,
            image_url=image_url,
            image_data_url=image_data_url,
            history=history,
            stage="background_result_fetch",
        )
        if history_id:
            complete_pending_history_item(history_id, result)
        else:
            create_history_item(
                request_data=request_data,
                prompts=prompts,
                result=result,
                payload_path=Path(payload_path),
                workflow_mode=workflow_mode,
            )
    except Exception:
        if history_id:
            update_pending_history_status(history_id, "failed", "Background history sync failed")
        traceback.print_exc()


def refresh_pending_history_items(addr: str, items: list[dict[str, Any]]) -> bool:
    pending_items = [item for item in items if is_pending_item(item)]
    if not pending_items:
        return False
    changed = False
    queue: dict[str, Any] = {}
    queue_available = False
    try:
        queue = comfy_client.queue_info(addr)
        queue_available = True
    except Exception:
        queue = {}
    for item in pending_items:
        prompt_id = str(item.get("prompt_id") or "")
        history_id = str(item.get("id") or "")
        if not prompt_id or not history_id:
            continue
        try:
            comfy_history = comfy_client.history_item(addr, prompt_id)
        except Exception:
            comfy_history = None
        if comfy_history:
            image = comfy_client.first_output_image(comfy_history)
            if image:
                try:
                    image_url, image_data_url = comfy_client.fetch_image_data_url(addr, image)
                    result = comfy_client.ComfyResult(
                        ok=True,
                        prompt_id=prompt_id,
                        image_url=image_url,
                        image_data_url=image_data_url,
                        history=comfy_history,
                        stage="history_refresh",
                    )
                    complete_pending_history_item(history_id, result)
                    changed = True
                    continue
                except Exception:
                    traceback.print_exc()
            update_pending_history_status(history_id, "failed", comfy_client.history_status_message(comfy_history))
            changed = True
            continue
        queue_status = comfy_client.queued_prompt_status(queue, prompt_id) if queue else None
        if queue_status:
            if item.get("status") != queue_status:
                update_pending_history_status(history_id, queue_status)
                changed = True
            continue
        if queue_available and pending_age_is_missing(item) and item.get("status") != "missing":
            update_pending_history_status(history_id, "missing", "Not found in ComfyUI queue or history")
            changed = True
            continue
        if pending_age_is_stale(item) and item.get("status") != "stale":
            update_pending_history_status(history_id, "stale", "Not found in ComfyUI queue or history")
            changed = True
    return changed


def history_page_with_flags(limit: int, offset: int, filter_name: str, search_filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[str], dict[str, Any], int]:
    all_items, warnings = list_all_history_with_warnings()
    attach_flags_to_items(all_items)
    filtered_items = filter_items_by_flags(all_items, filter_name)
    normalized_offset = max(0, int(offset or 0))
    page_limit = max(1, min(int(limit or 20), 100))
    if search_filters:
        page_items, filtered_total = search_history_items(filtered_items, limit=page_limit, offset=normalized_offset, **search_filters)
    else:
        page_items = filtered_items[normalized_offset : normalized_offset + page_limit]
        filtered_total = len(filtered_items)
    summary = summarize_history(all_items)
    summary.update(flag_summary(all_items))
    summary["filtered_total"] = filtered_total
    summary["filter"] = filter_name or "all"
    summary["query"] = search_filters or {}
    return page_items, warnings, summary, filtered_total


def prepare_reference_request(request_data: dict[str, Any], addr: str, *, upload: bool) -> dict[str, Any]:
    ref = reference_store.sanitize_reference_assist(request_data.get("reference_assist"), app_scope="anima", default_strength=0.25)
    caps = reference_capability_payload(addr)
    ref["capability"] = caps.get("reference_assist", {})
    controlnet = ref["capability"].get("modes", {}).get("controlnet", {})
    ref["supported"] = bool(controlnet.get("supported"))
    ref["apply_node_type"] = controlnet.get("apply_node_type") or ""
    ref["has_union_type"] = bool(controlnet.get("has_union_type"))
    if not ref.get("controlnet_model"):
        models = ref["capability"].get("controlnet_models") or []
        ref["controlnet_model"] = models[0] if models else ""
    if ref.get("image_id"):
        image = reference_store.get_reference_image(ref["image_id"])
        if image:
            ref["image_name"] = image.get("filename") or ""
            ref["thumbnail_url"] = image.get("thumbnail_url") or ""
            ref["image_url"] = image.get("image_url") or ""
            ref["comfyui_image"] = image.get("comfyui_image") or ref.get("comfyui_image") or {}
            comfy_name = str((ref.get("comfyui_image") or {}).get("name") or "")
            if upload and not comfy_name:
                image_path = Path(str(image.get("path") or ""))
                if image_path.exists():
                    result = comfy_client.upload_image(addr, filename=image.get("filename") or image_path.name, data=image_path.read_bytes())
                    ref["comfyui_upload"] = {"ok": result.get("ok"), "status": result.get("status"), "message": result.get("text", "")[:500]}
                    if result.get("ok"):
                        updated = reference_store.update_comfy_upload(ref["image_id"], result) or image
                        ref["comfyui_image"] = updated.get("comfyui_image") or {}
    comfy_name = str((ref.get("comfyui_image") or {}).get("name") or "")
    ref["apply_to_payload"] = bool(
        ref.get("enabled")
        and ref.get("experimental")
        and ref.get("supported")
        and comfy_name
        and ref.get("controlnet_model")
    )
    if ref.get("enabled") and not ref["apply_to_payload"]:
        missing = []
        if not ref.get("experimental"):
            missing.append("experimental_guard")
        if not ref.get("supported"):
            missing.extend(controlnet.get("missing_nodes") or ["controlnet"])
        if not ref.get("image_id"):
            missing.append("reference_image")
        if ref.get("image_id") and not comfy_name:
            missing.append("comfyui_image_upload")
        if not ref.get("controlnet_model"):
            missing.append("controlnet_model")
        ref["unsupported_reason"] = ", ".join(str(item) for item in missing if item)
    request_data["reference_assist"] = ref
    return request_data


def prepare_reference_modules_request(request_data: dict[str, Any], addr: str, *, upload: bool) -> dict[str, Any]:
    modules = sanitize_reference_modules(request_data.get("reference_modules"), app_scope="anima")
    caps = reference_modules_availability_payload(addr)
    outfit_caps = (caps.get("reference_modules") or {}).get("outfit") or {}
    pose_caps = (caps.get("reference_modules") or {}).get("pose") or {}
    background_caps = (caps.get("reference_modules") or {}).get("background") or {}
    outfit = modules.get("outfit") if isinstance(modules.get("outfit"), dict) else {}
    outfit["availability"] = outfit_caps
    outfit["available"] = bool(outfit_caps.get("available"))
    outfit["apply_node"] = outfit_caps.get("apply_node") or outfit.get("apply_node") or "easy ipadapterApply"
    warnings = list(outfit_caps.get("warnings") or [])
    if outfit.get("enabled"):
        if not outfit.get("available"):
            outfit["unsupported_reason"] = "; ".join(warnings or ["required IP-Adapter nodes are unavailable"])
        if outfit.get("image_id"):
            image = reference_store.get_reference_image(outfit["image_id"])
            if image:
                outfit["image_name"] = image.get("filename") or ""
                outfit["image_filename"] = image.get("filename") or ""
                outfit["thumbnail_url"] = image.get("thumbnail_url") or ""
                outfit["image_url"] = image.get("image_url") or ""
                outfit["comfyui_image"] = image.get("comfyui_image") or outfit.get("comfyui_image") or {}
                comfy_name = str((outfit.get("comfyui_image") or {}).get("name") or "")
                if upload and not comfy_name:
                    image_path = Path(str(image.get("path") or ""))
                    if image_path.exists():
                        result = comfy_client.upload_image(addr, filename=image.get("filename") or image_path.name, data=image_path.read_bytes())
                        outfit["comfyui_upload"] = {"ok": result.get("ok"), "status": result.get("status"), "message": result.get("text", "")[:500]}
                        if result.get("ok"):
                            updated = reference_store.update_comfy_upload(outfit["image_id"], result) or image
                            outfit["comfyui_image"] = updated.get("comfyui_image") or {}
                            outfit["image_name"] = updated.get("filename") or outfit.get("image_name") or ""
        comfy_name = str((outfit.get("comfyui_image") or {}).get("name") or "")
        outfit["apply_to_payload"] = bool(outfit.get("available") and outfit.get("image_id") and comfy_name)
        missing: list[str] = []
        if not outfit.get("image_id"):
            missing.append("outfit_reference_image")
        if outfit.get("image_id") and not comfy_name:
            missing.append("comfyui_image_upload")
        if not outfit.get("available"):
            missing.extend(outfit_caps.get("missing_nodes") or ["ip_adapter"])
        if missing:
            outfit["unsupported_reason"] = ", ".join(str(item) for item in missing if item)
    else:
        outfit["apply_to_payload"] = False
    outfit["warnings"] = warnings
    modules["outfit"] = outfit
    pose = modules.get("pose") if isinstance(modules.get("pose"), dict) else {}
    pose["availability"] = pose_caps
    pose["available"] = bool(pose_caps.get("available"))
    pose_warnings = list(pose_caps.get("warnings") or [])
    pose_mode = str(pose.get("mode") or "pose_image")
    mode_caps = (pose_caps.get("modes") or {}).get(pose_mode) or {}
    pose["controlnet_model"] = pose.get("controlnet_model") or pose_caps.get("controlnet_model") or ""
    pose["requires_union_type"] = bool(pose_caps.get("requires_union_type"))
    pose["union_type"] = pose_caps.get("union_type") or pose.get("union_type") or "openpose"
    if pose.get("enabled"):
        if not mode_caps.get("available"):
            pose["unsupported_reason"] = "; ".join(pose_warnings or mode_caps.get("missing_nodes") or ["pose mode unavailable"])
        if pose.get("image_id"):
            image = reference_store.get_reference_image(pose["image_id"])
            if image:
                pose["image_name"] = image.get("filename") or ""
                pose["image_filename"] = image.get("filename") or ""
                pose["thumbnail_url"] = image.get("thumbnail_url") or ""
                pose["image_url"] = image.get("image_url") or ""
                pose["comfyui_image"] = image.get("comfyui_image") or pose.get("comfyui_image") or {}
                comfy_name = str((pose.get("comfyui_image") or {}).get("name") or "")
                if upload and not comfy_name:
                    image_path = Path(str(image.get("path") or ""))
                    if image_path.exists():
                        result = comfy_client.upload_image(addr, filename=image.get("filename") or image_path.name, data=image_path.read_bytes())
                        pose["comfyui_upload"] = {"ok": result.get("ok"), "status": result.get("status"), "message": result.get("text", "")[:500]}
                        if result.get("ok"):
                            updated = reference_store.update_comfy_upload(pose["image_id"], result) or image
                            pose["comfyui_image"] = updated.get("comfyui_image") or {}
                            pose["image_name"] = updated.get("filename") or pose.get("image_name") or ""
        comfy_name = str((pose.get("comfyui_image") or {}).get("name") or "")
        pose["apply_to_payload"] = bool(pose.get("available") and mode_caps.get("available") and pose.get("image_id") and comfy_name and pose.get("controlnet_model"))
        missing = []
        if not pose.get("image_id"):
            missing.append("pose_reference_image")
        if pose.get("image_id") and not comfy_name:
            missing.append("comfyui_image_upload")
        if not mode_caps.get("available"):
            missing.extend(mode_caps.get("missing_nodes") or pose_caps.get("missing_nodes") or ["pose_controlnet"])
        if not pose.get("controlnet_model"):
            missing.append("controlnet_model")
        if missing:
            pose["unsupported_reason"] = ", ".join(str(item) for item in missing if item)
    else:
        pose["apply_to_payload"] = False
    pose["warnings"] = pose_warnings
    modules["pose"] = pose
    background = modules.get("background") if isinstance(modules.get("background"), dict) else {}
    background["availability"] = background_caps
    background["available"] = bool(background_caps.get("available"))
    background_warnings = list(background_caps.get("warnings") or [])
    background_mode = str(background.get("mode") or "depth")
    background_mode_caps = (background_caps.get("modes") or {}).get(background_mode) or {}
    background["controlnet_model"] = (
        background.get("controlnet_model")
        if background.get("controlnet_model") and str(background.get("controlnet_model")).lower() != "auto"
        else background_mode_caps.get("controlnet_model") or ""
    )
    background["preprocessor_node_class"] = background_mode_caps.get("preprocessor_node_class") or background.get("preprocessor_node_class") or ""
    background["preprocessor_inputs"] = background_mode_caps.get("preprocessor_inputs") or background.get("preprocessor_inputs") or {}
    background["apply_node_class"] = background_caps.get("apply_node") or background.get("apply_node_class") or "ControlNetApplyAdvanced"
    background["loader_node_class"] = background_caps.get("loader_node") or background.get("loader_node_class") or "ControlNetLoader"
    background["image_resize_node_class"] = background_caps.get("image_resize_node") or background.get("image_resize_node_class") or ""
    if background.get("enabled") and background.get("resize_mode") == "fit" and background.get("image_resize_node_class") == "ImageScale":
        background_warnings.append("Background resize fit uses ImageScale without padding; use crop for center crop or stretch for exact scaling.")
    if background.get("enabled"):
        if not background_mode_caps.get("available"):
            reason_parts = [*background_warnings, *(background_mode_caps.get("missing_nodes") or background_caps.get("missing_nodes") or ["background_controlnet"])]
            background["unsupported_reason"] = "; ".join(str(item) for item in reason_parts if item)
        if background.get("image_id"):
            image = reference_store.get_reference_image(background["image_id"])
            if image:
                background["image_name"] = image.get("filename") or ""
                background["image_filename"] = image.get("filename") or ""
                background["thumbnail_url"] = image.get("thumbnail_url") or ""
                background["image_url"] = image.get("image_url") or ""
                background["comfyui_image"] = image.get("comfyui_image") or background.get("comfyui_image") or {}
                comfy_name = str((background.get("comfyui_image") or {}).get("name") or "")
                if upload and not comfy_name:
                    image_path = Path(str(image.get("path") or ""))
                    if image_path.exists():
                        result = comfy_client.upload_image(addr, filename=image.get("filename") or image_path.name, data=image_path.read_bytes())
                        background["comfyui_upload"] = {"ok": result.get("ok"), "status": result.get("status"), "message": result.get("text", "")[:500]}
                        if result.get("ok"):
                            updated = reference_store.update_comfy_upload(background["image_id"], result) or image
                            background["comfyui_image"] = updated.get("comfyui_image") or {}
                            background["image_name"] = updated.get("filename") or background.get("image_name") or ""
        comfy_name = str((background.get("comfyui_image") or {}).get("name") or "")
        background["apply_to_payload"] = bool(
            background.get("available")
            and background_mode_caps.get("available")
            and background.get("image_id")
            and comfy_name
            and background.get("controlnet_model")
            and background.get("preprocessor_node_class")
        )
        missing = []
        if not background.get("image_id"):
            missing.append("background_reference_image")
        if background.get("image_id") and not comfy_name:
            missing.append("comfyui_image_upload")
        if not background_mode_caps.get("available"):
            missing.extend(background_mode_caps.get("missing_nodes") or background_caps.get("missing_nodes") or ["background_controlnet"])
        if not background.get("controlnet_model"):
            missing.append("controlnet_model")
        if not background.get("preprocessor_node_class"):
            missing.append("background_preprocessor")
        if missing:
            background["unsupported_reason"] = ", ".join(str(item) for item in missing if item)
    else:
        background["apply_to_payload"] = False
    background["warnings"] = background_warnings
    modules["background"] = background
    request_data["reference_modules"] = modules
    return request_data


def prepare_i2i_request(request_data: dict[str, Any], addr: str, *, upload: bool) -> dict[str, Any]:
    i2i = i2i_store.sanitize_image_to_image(request_data.get("image_to_image"), app_scope="anima")
    caps = i2i_capability_payload(addr)
    i2i["capability"] = caps.get("image_to_image", {})
    i2i["supported"] = bool(i2i["capability"].get("supported"))
    if i2i.get("enabled") and i2i.get("image_id"):
        try:
            prepared = i2i_store.prepare_i2i_image(
                i2i["image_id"],
                width=int(request_data.get("width") or 1024),
                height=int(request_data.get("height") or 1536),
                resize_mode=i2i.get("resize_mode") or "fit",
                use_source_size=bool(i2i.get("use_source_size")),
            )
            if i2i.get("use_source_size"):
                request_data["width"] = prepared["prepared_width"]
                request_data["height"] = prepared["prepared_height"]
            entry = prepared.get("prepared") if isinstance(prepared.get("prepared"), dict) else {}
            comfy = entry.get("comfyui_image") if isinstance(entry.get("comfyui_image"), dict) else {}
            if upload and not comfy.get("name"):
                prepared_path = Path(str(prepared.get("prepared_path") or ""))
                if prepared_path.is_file():
                    result = comfy_client.upload_image(addr, filename=prepared.get("prepared_filename") or prepared_path.name, data=prepared_path.read_bytes(), overwrite=True)
                    i2i["comfyui_upload"] = {"ok": result.get("ok"), "status": result.get("status"), "message": result.get("text", "")[:500]}
                    if result.get("ok"):
                        updated = i2i_store.update_prepared_comfy_upload(i2i["image_id"], prepared["prepared_key"], result)
                        if updated:
                            prepared = i2i_store.prepare_i2i_image(
                                i2i["image_id"],
                                width=int(request_data.get("width") or 1024),
                                height=int(request_data.get("height") or 1536),
                                resize_mode=i2i.get("resize_mode") or "fit",
                                use_source_size=False,
                            )
                            entry = prepared.get("prepared") if isinstance(prepared.get("prepared"), dict) else {}
                            comfy = entry.get("comfyui_image") if isinstance(entry.get("comfyui_image"), dict) else {}
                    else:
                        i2i["unsupported_reason"] = str(result.get("text") or "ComfyUI image upload failed")[:500]
                else:
                    i2i["unsupported_reason"] = "prepared i2i image file not found"
            comfy_for_payload = comfy if comfy.get("name") else ({"name": prepared.get("prepared_filename"), "subfolder": "", "type": "input"} if not upload else {})
            i2i.update(
                {
                    "source": prepared.get("source") or i2i.get("source"),
                    "source_history_id": prepared.get("source_history_id") or i2i.get("source_history_id"),
                    "image_url": prepared.get("image_url") or "",
                    "thumbnail_url": prepared.get("thumbnail_url") or "",
                    "source_width": prepared.get("source_width"),
                    "source_height": prepared.get("source_height"),
                    "prepared_width": prepared.get("prepared_width"),
                    "prepared_height": prepared.get("prepared_height"),
                    "prepared_key": prepared.get("prepared_key"),
                    "prepared_filename": prepared.get("prepared_filename"),
                    "comfyui_image": comfy_for_payload,
                }
            )
        except Exception as exc:
            i2i["unsupported_reason"] = str(exc)
    comfy_name = str((i2i.get("comfyui_image") or {}).get("name") or "")
    i2i["apply_to_payload"] = bool(i2i.get("enabled") and i2i.get("supported") and i2i.get("image_id") and comfy_name)
    if i2i.get("enabled") and not i2i["apply_to_payload"]:
        missing: list[str] = []
        if not i2i.get("supported"):
            missing.extend(i2i.get("capability", {}).get("missing_nodes") or ["i2i_nodes"])
        if not i2i.get("image_id"):
            missing.append("i2i_image")
        if i2i.get("image_id") and not comfy_name:
            missing.append("comfyui_image_upload")
        if i2i.get("unsupported_reason"):
            missing.append(str(i2i.get("unsupported_reason")))
        i2i["unsupported_reason"] = ", ".join(str(item) for item in missing if item)
    request_data["image_to_image"] = i2i
    return request_data
