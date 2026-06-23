from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Cookie, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import comfy_client, reference_store
from ..anima_adapter import load_settings
from ..auth import require_auth
from ..config import COMFYUI_ADDR_DEFAULT
from ..generation_prepare import (
    face_detailer_capability_payload,
    reference_capability_payload,
    reference_modules_availability_payload,
    reference_modules_model_status_payload,
)
from ..reference_modules import REFERENCE_MODULE_NAMES

router = APIRouter()

@router.get("/api/reference/capabilities")
def reference_capabilities(refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    payload = reference_capability_payload(addr, refresh=refresh)
    payload.setdefault("reference_assist", {})["anima_payload_guard"] = "experimental_required"
    return payload


@router.get("/api/reference-modules/availability")
def reference_modules_availability(refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    return reference_modules_availability_payload(addr, refresh=refresh)


@router.get("/api/reference-modules/model-status")
def reference_modules_model_status(refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    return reference_modules_model_status_payload(addr, refresh=refresh)


@router.get("/api/face-detailer/capabilities")
def face_detailer_capability_endpoint(refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    return face_detailer_capability_payload(addr, refresh=refresh)


@router.get("/api/reference/images")
def reference_images(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "items": reference_store.list_reference_images()}


@router.get("/api/reference-modules/images")
def reference_module_images(module: str = "outfit", anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "items": reference_store.list_reference_images(module=module)}


@router.post("/api/reference/upload")
async def reference_upload(file: UploadFile = File(...), anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    try:
        filename = file.filename or "reference.png"
        raw = await file.read()
        item = reference_store.save_reference_upload(filename or "reference.png", raw, app_scope="anima")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    upload_result = comfy_client.upload_image(addr, filename=item["filename"], data=Path(item["path"]).read_bytes())
    if upload_result.get("ok"):
        item = reference_store.update_comfy_upload(item["image_id"], upload_result) or item
    return {
        "ok": True,
        "item": item,
        "comfyui_upload": {
            "ok": bool(upload_result.get("ok")),
            "status": upload_result.get("status"),
            "message": str(upload_result.get("text") or "")[:500],
        },
    }


@router.post("/api/reference-modules/upload")
async def reference_module_upload(file: UploadFile = File(...), module: str = "outfit", anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    if module not in REFERENCE_MODULE_NAMES:
        raise HTTPException(status_code=400, detail="Only outfit, pose, and background reference module uploads are implemented.")
    try:
        filename = file.filename or ""
        raw = await file.read()
        default_name = f"{module}_reference.png"
        item = reference_store.save_reference_upload(filename or default_name, raw, app_scope="anima", module=module)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    upload_result = comfy_client.upload_image(addr, filename=item["filename"], data=Path(item["path"]).read_bytes())
    if upload_result.get("ok"):
        item = reference_store.update_comfy_upload(item["image_id"], upload_result) or item
    return {
        "ok": True,
        "item": item,
        "items": reference_store.list_reference_images(module=module),
        "comfyui_upload": {
            "ok": bool(upload_result.get("ok")),
            "status": upload_result.get("status"),
            "message": str(upload_result.get("text") or "")[:500],
        },
    }


@router.post("/api/reference-modules/clear")
def reference_module_clear(module: str = "outfit", anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    if module not in REFERENCE_MODULE_NAMES:
        raise HTTPException(status_code=400, detail="Only outfit, pose, and background reference modules are implemented.")
    return {"ok": True, "module": module, "items": reference_store.list_reference_images(module=module)}


@router.get("/api/reference/images/{image_id}/image")
def reference_image(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = reference_store.get_reference_image(image_id)
    if not item:
        raise HTTPException(status_code=404, detail="reference image not found")
    path = Path(str(item.get("path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="reference image file not found")
    return FileResponse(path)


@router.get("/api/reference/images/{image_id}/thumbnail")
def reference_thumbnail(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = reference_store.get_reference_image(image_id)
    if not item:
        raise HTTPException(status_code=404, detail="reference image not found")
    path = Path(str(item.get("thumbnail_path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="reference thumbnail not found")
    return FileResponse(path)


@router.delete("/api/reference/images/{image_id}")
def reference_delete(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "deleted": reference_store.delete_reference_image(image_id)}
