from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie
from fastapi.responses import JSONResponse

from ..auth import require_auth
from ..comfyui_control import latest_restart_status, restart_capability, start_restart

router = APIRouter()


@router.get("/api/system/comfyui/restart-capability")
def comfy_restart_capability(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return restart_capability()


@router.post("/api/system/comfyui/restart")
def comfy_restart(anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    result = start_restart()
    status_code = 200 if result.get("ok") else 400
    return JSONResponse(status_code=status_code, content=result)


@router.get("/api/system/comfyui/restart-status")
def comfy_restart_status(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return latest_restart_status()
