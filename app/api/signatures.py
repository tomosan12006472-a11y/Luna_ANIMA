from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Cookie, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..auth import require_auth
from ..signature_store import (
    delete_signature,
    get_signature,
    list_signatures,
    save_signature_upload,
    signature_image_path,
    signature_thumbnail_path,
)

router = APIRouter()


def signature_file_response(path: Path, media_type: str = "image/png") -> FileResponse:
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store, max-age=0, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.get("/api/signatures")
def signatures(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "items": list_signatures()}


@router.post("/api/signatures/upload")
async def signature_upload(file: UploadFile = File(...), anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    try:
        item = save_signature_upload(file.filename or "signature.png", await file.read())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "item": item}


@router.get("/api/signatures/{signature_id}/image")
def signature_image(signature_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    if not get_signature(signature_id):
        raise HTTPException(status_code=404, detail="signature image not found")
    path = signature_image_path(signature_id)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="signature image file not found")
    return signature_file_response(Path(path), media_type="image/png")


@router.get("/api/signatures/{signature_id}/thumbnail")
def signature_thumbnail(signature_id: str, anima_claude_session: str | None = Cookie(default=None)) -> FileResponse:
    require_auth(anima_claude_session)
    if not get_signature(signature_id):
        raise HTTPException(status_code=404, detail="signature image not found")
    path = signature_thumbnail_path(signature_id)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="signature thumbnail not found")
    return signature_file_response(Path(path), media_type="image/png")


@router.delete("/api/signatures/{signature_id}")
def signature_delete(signature_id: str, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "deleted": delete_signature(signature_id)}
