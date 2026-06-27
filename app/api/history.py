from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
import traceback
from typing import Any
import uuid

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse

from .. import comfy_client
from ..anima_adapter import load_settings
from ..auth import require_auth
from ..config import COMFYUI_ADDR_DEFAULT
from ..detailer_postprocess import (
    build_face_detailer_postprocess_request,
    build_hand_detailer_postprocess_request,
)
from ..generation_prepare import (
    face_detailer_capability_payload,
    history_page_with_flags,
    refresh_pending_history_items,
    save_completed_generation_history,
    save_mobile_payload_data,
)
from ..history_flags_store import attach_flags_to_item, update_history_flags
from ..history_store import (
    copy_public_image,
    create_pending_history_item,
    enrich_history_item_from_payload,
    ensure_small_thumbnail,
    history_collection_revision,
    lite_history_item,
    load_history_item,
    resolve_public_image_path,
)
from ..payload_builder import (
    build_face_detailer_postprocess_payload,
    build_hand_detailer_postprocess_payload,
)
from ..responses import cached_file_response, resolve_public_save_finish, resolve_public_save_watermark
from ..schemas.generation import FaceDetailerPostprocessRequest, HandDetailerPostprocessRequest
from ..schemas.history import HistoryFlagsRequest, PublicSaveRequest
from ..settings_store import load_app_settings
from ..public_save_jobs import public_save_status, start_public_save_job

router = APIRouter()


def mutable_file_response(path: Path, media_type: str | None = None) -> FileResponse:
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store, max-age=0, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.get("/api/history")
def history(
    response: Response,
    limit: int = 100,
    offset: int = 0,
    view: str = "",
    filter_name: str = Query("all", alias="filter"),
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    model: str = "",
    lora: str = "",
    seed: str = "",
    hires_mode: str = "",
    reference: str = "",
    sampler: str = "",
    scheduler: str = "",
    rating: str = "",
    character: str = "",
    known_revision: str = "",
    anima_claude_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    require_auth(anima_claude_session)
    if not isinstance(filter_name, str):
        filter_name = "all"
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    search_filters = {
        "q": q,
        "date_from": date_from,
        "date_to": date_to,
        "model": model,
        "lora": lora,
        "seed": seed,
        "hires_mode": hires_mode,
        "reference": reference,
        "sampler": sampler,
        "scheduler": scheduler,
        "rating": rating,
        "character": character,
    }
    search_filters = {key: value for key, value in search_filters.items() if str(value or "").strip()}
    items, warnings, summary, total = history_page_with_flags(limit, offset, filter_name, search_filters)
    if refresh_pending_history_items(addr, items):
        items, warnings, summary, total = history_page_with_flags(limit, offset, filter_name, search_filters)
    normalized_offset = max(0, int(offset or 0))
    response_items = [lite_history_item(item) for item in items] if str(view or "").lower() == "list" else items
    latest = response_items[0] if response_items else {}
    latest_id = str(latest.get("id") or "")
    latest_created_at = str(latest.get("created_at") or "")
    response_limit = max(1, min(int(limit or 100), 100))
    revision = ":".join(
        [
            history_collection_revision(),
            str(view or ""),
            str(filter_name or "all"),
            str(response_limit),
            str(normalized_offset),
            json.dumps(search_filters, ensure_ascii=False, sort_keys=True),
        ]
    )
    response.headers["Cache-Control"] = "no-store, max-age=0"
    if str(known_revision or "").strip() == revision:
        return {"ok": True, "unchanged": True, "revision": revision}
    return {
        "ok": True,
        "unchanged": False,
        "items": response_items,
        "warnings": warnings,
        "summary": summary,
        "total": total,
        "filtered_total": total,
        "query": {"filter": filter_name or "all", **search_filters, **({"view": "list"} if str(view or "").lower() == "list" else {})},
        "limit": response_limit,
        "offset": normalized_offset,
        "has_more": normalized_offset + len(items) < total,
        "latest_id": latest_id,
        "latest_created_at": latest_created_at,
        "revision": revision,
    }


@router.get("/api/history/{history_id}")
def history_detail(history_id: str, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    enrich_history_item_from_payload(item)
    attach_flags_to_item(item)
    return {"ok": True, "item": item}


@router.post("/api/face-detailer/postprocess")
def face_detailer_postprocess(
    data: FaceDetailerPostprocessRequest,
    background_tasks: BackgroundTasks,
    anima_claude_session: str | None = Cookie(default=None),
) -> JSONResponse:
    require_auth(anima_claude_session)
    item = load_history_item(data.history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    image_path = Path(str(item.get("image_path") or ""))
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="source image not found")
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    caps = face_detailer_capability_payload(addr).get("face_detailer", {})
    if not caps.get("supported"):
        return JSONResponse(status_code=400, content={"ok": False, "message": "FaceDetailer is not available.", "face_detailer": caps})
    request_data, prompts, warnings = build_face_detailer_postprocess_request(item, data.settings)
    digest = hashlib.sha256(f"{item.get('id')}:{time.time()}".encode("utf-8")).hexdigest()[:10]
    upload_name = f"anima_face_detailer_{item.get('id')}_{digest}{image_path.suffix or '.png'}"
    upload_result = comfy_client.upload_image(addr, filename=upload_name, data=image_path.read_bytes(), overwrite=True)
    if not upload_result.get("ok"):
        return JSONResponse(status_code=502, content={"ok": False, "message": "Failed to upload source image to ComfyUI.", "upload": upload_result})
    uploaded = upload_result.get("json") if isinstance(upload_result.get("json"), dict) else {}
    image_name = str(uploaded.get("name") or upload_name)
    client_id = f"anima-face-detailer-{uuid.uuid4()}"
    try:
        payload = build_face_detailer_postprocess_payload(request_data, client_id, image_name)
        dump_path = save_mobile_payload_data(payload, request_data, "face_detailer_postprocess")
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(status_code=400, content={"ok": False, "message": str(exc), "stage": "build_face_detailer_payload"})
    result = comfy_client.run_generation(addr, payload, wait=False)
    if not result.ok:
        return JSONResponse(status_code=502, content={"ok": False, "message": result.error or "FaceDetailer queue failed", "stage": result.stage, "comfy_node_errors": result.node_errors})
    pending_item = None
    if result.prompt_id:
        pending_item = create_pending_history_item(
            request_data=request_data,
            prompts=prompts,
            prompt_id=result.prompt_id,
            payload_path=dump_path,
            workflow_mode="face_detailer_postprocess",
            index=0,
        )
        background_tasks.add_task(
            save_completed_generation_history,
            addr=addr,
            request_data=request_data,
            prompts=prompts,
            prompt_id=result.prompt_id,
            payload_path=str(dump_path),
            workflow_mode="face_detailer_postprocess",
            history_id=pending_item["id"],
        )
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "queued": True,
            "prompt_id": result.prompt_id,
            "pending_history_id": pending_item["id"] if pending_item else None,
            "parent_history_id": item.get("id"),
            "warnings": warnings,
            "face_detailer": request_data.get("face_detailer", {}),
        },
    )


@router.post("/api/hand-detailer/postprocess")
def hand_detailer_postprocess(
    data: HandDetailerPostprocessRequest,
    background_tasks: BackgroundTasks,
    anima_claude_session: str | None = Cookie(default=None),
) -> JSONResponse:
    require_auth(anima_claude_session)
    item = load_history_item(data.history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    image_path = Path(str(item.get("image_path") or ""))
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="source image not found")
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    caps = face_detailer_capability_payload(addr).get("face_detailer", {})
    hand_caps = caps.get("hand_detailer") if isinstance(caps.get("hand_detailer"), dict) else {}
    if not caps.get("hand_supported"):
        return JSONResponse(status_code=400, content={"ok": False, "message": "Hand Detailer is not available.", "face_detailer": caps, "hand_detailer": hand_caps})
    request_data, prompts, warnings = build_hand_detailer_postprocess_request(item, data.settings)
    digest = hashlib.sha256(f"{item.get('id')}:{time.time()}".encode("utf-8")).hexdigest()[:10]
    upload_name = f"anima_hand_detailer_{item.get('id')}_{digest}{image_path.suffix or '.png'}"
    upload_result = comfy_client.upload_image(addr, filename=upload_name, data=image_path.read_bytes(), overwrite=True)
    if not upload_result.get("ok"):
        return JSONResponse(status_code=502, content={"ok": False, "message": "Failed to upload source image to ComfyUI.", "upload": upload_result})
    uploaded = upload_result.get("json") if isinstance(upload_result.get("json"), dict) else {}
    image_name = str(uploaded.get("name") or upload_name)
    client_id = f"anima-hand-detailer-{uuid.uuid4()}"
    try:
        payload = build_hand_detailer_postprocess_payload(request_data, client_id, image_name)
        dump_path = save_mobile_payload_data(payload, request_data, "hand_detailer_postprocess")
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(status_code=400, content={"ok": False, "message": str(exc), "stage": "build_hand_detailer_payload"})
    result = comfy_client.run_generation(addr, payload, wait=False)
    if not result.ok:
        return JSONResponse(status_code=502, content={"ok": False, "message": result.error or "Hand Detailer queue failed", "stage": result.stage, "comfy_node_errors": result.node_errors})
    pending_item = None
    if result.prompt_id:
        pending_item = create_pending_history_item(
            request_data=request_data,
            prompts=prompts,
            prompt_id=result.prompt_id,
            payload_path=dump_path,
            workflow_mode="hand_detailer_postprocess",
            index=0,
        )
        background_tasks.add_task(
            save_completed_generation_history,
            addr=addr,
            request_data=request_data,
            prompts=prompts,
            prompt_id=result.prompt_id,
            payload_path=str(dump_path),
            workflow_mode="hand_detailer_postprocess",
            history_id=pending_item["id"],
        )
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "queued": True,
            "prompt_id": result.prompt_id,
            "pending_history_id": pending_item["id"] if pending_item else None,
            "parent_history_id": item.get("id"),
            "warnings": warnings,
            "hand_detailer": request_data.get("hand_detailer", {}),
        },
    )


@router.post("/api/history/{history_id}/flags")
def history_flags(history_id: str, data: HistoryFlagsRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    patch = dict(data.patch or {})
    for key in ("favorite", "post_candidate", "hidden", "tags"):
        value = getattr(data, key)
        if value is not None:
            patch[key] = value
    item["flags"] = update_history_flags(history_id, patch)
    return {"ok": True, "item": item, "flags": item["flags"]}


@router.get("/api/history/{history_id}/image")
def history_image(history_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    path = Path(item["image_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="image not found")
    return cached_file_response(path)


@router.get("/api/history/{history_id}/thumbnail")
def history_thumbnail(history_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    path = Path(item["thumbnail_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="thumbnail not found")
    return cached_file_response(path, media_type="image/jpeg")


@router.get("/api/history/{history_id}/thumbnail-small")
def history_thumbnail_small(history_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    path = ensure_small_thumbnail(item)
    if not path or not path.exists():
        fallback = Path(str(item.get("thumbnail_path") or ""))
        if not fallback.exists():
            raise HTTPException(status_code=404, detail="thumbnail not found")
        return cached_file_response(fallback, media_type="image/jpeg")
    return cached_file_response(path, media_type="image/jpeg")


@router.get("/api/history/{history_id}/public-image")
def history_public_image(history_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    path = resolve_public_image_path(item)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="public image not found")
    return mutable_file_response(path)


@router.post("/api/history/{history_id}/public-save")
def public_save(history_id: str, data: PublicSaveRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    app_settings = load_app_settings()
    watermark = resolve_public_save_watermark(data, app_settings)
    finish = resolve_public_save_finish(data, app_settings)
    source = Path(str(item.get("image_path") or ""))
    if not source.exists():
        public_save_info = item.get("public_save") if isinstance(item.get("public_save"), dict) else {}
        if public_save_info.get("saved") and resolve_public_image_path(item):
            if data.async_save:
                return public_save_status(history_id, None)
            public_image_url = item.get("public_image_url") or public_save_info.get("url")
            return {
                "ok": True,
                "public_save": public_save_info,
                "public_image_url": public_image_url,
                "filename": public_save_info.get("filename") or f"{history_id}_public.png",
                "item": item,
            }
        raise HTTPException(status_code=404, detail="source image not found")
    if data.async_save:
        result = start_public_save_job(history_id, item, watermark, finish)
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail=result.get("message") or "public save conflict")
        return result
    public_info = copy_public_image(item, watermark, finish)
    updated = load_history_item(history_id) or item
    public_image_url = updated.get("public_image_url") or public_info.get("url")
    return {
        "ok": True,
        "public_save": public_info,
        "public_image_url": public_image_url,
        "filename": public_info.get("filename") or f"{history_id}_public.png",
        "item": updated,
    }


@router.get("/api/history/{history_id}/public-save/status")
def public_save_status_endpoint(
    history_id: str,
    job_id: str = "",
    anima_claude_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = load_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    result = public_save_status(history_id, job_id or None)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("message") or "public save job not found")
    return result
