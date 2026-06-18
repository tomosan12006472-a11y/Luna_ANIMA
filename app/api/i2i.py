from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Cookie, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from .. import i2i_store
from ..anima_adapter import load_settings
from ..auth import require_auth
from ..config import COMFYUI_ADDR_DEFAULT
from ..generation_prepare import i2i_capability_payload
from ..history_store import load_history_item
from ..schemas.reference import I2IFromHistoryRequest

router = APIRouter()

@router.get("/api/i2i/capabilities")
def i2i_capabilities_endpoint(refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    return i2i_capability_payload(addr, refresh=refresh)


@router.get("/api/i2i/images")
def i2i_images(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "items": i2i_store.list_i2i_images(limit=limit, offset=offset)}


@router.post("/api/i2i/upload")
async def i2i_upload(file: UploadFile = File(...), anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    try:
        filename = file.filename or "i2i.png"
        raw = await file.read()
        item = i2i_store.save_i2i_upload(filename or "i2i.png", raw, app_scope="anima")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "item": item}


@router.post("/api/i2i/from-history")
def i2i_from_history(data: I2IFromHistoryRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = load_history_item(data.history_id)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    path = Path(str(item.get("image_path") or ""))
    try:
        i2i_item = i2i_store.save_i2i_from_path(path, app_scope="anima", source_history_id=str(item.get("id") or data.history_id))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "item": i2i_item}


@router.get("/api/i2i/images/{image_id}/image")
def i2i_image(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = i2i_store.get_i2i_image(image_id)
    if not item:
        raise HTTPException(status_code=404, detail="i2i image not found")
    path = Path(str(item.get("path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="i2i image file not found")
    return FileResponse(path)


@router.get("/api/i2i/images/{image_id}/thumbnail")
def i2i_thumbnail(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    item = i2i_store.get_i2i_image(image_id)
    if not item:
        raise HTTPException(status_code=404, detail="i2i image not found")
    path = Path(str(item.get("thumbnail_path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="i2i thumbnail not found")
    return FileResponse(path)


@router.delete("/api/i2i/images/{image_id}")
def i2i_delete(image_id: str, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "deleted": i2i_store.delete_i2i_image(image_id)}
