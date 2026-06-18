from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie, Response
from fastapi.responses import FileResponse, HTMLResponse

from ..anima_adapter import catalog, load_settings
from ..auth import create_session_token, require_auth, set_session_cookie, validate_login_pin
from ..capabilities import anima_shift_capability
from ..config import (
    ANIMA_MAPPING_PATH,
    ANIMA_WORKFLOW_PATH,
    CHARACTER_CATALOG_ROOT,
    COMFYUI_ADDR_DEFAULT,
    ROOT_DIR,
)
from ..payload_builder import NEGATIVE_PRESETS
from ..schemas.auth import LoginRequest
from ..settings_store import load_app_settings

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(
        ROOT_DIR / "app" / "static" / "index.html",
        headers={"Cache-Control": "no-cache, max-age=0, must-revalidate"},
    )


@router.post("/api/login")
def login(data: LoginRequest, response: Response) -> dict[str, Any]:
    validate_login_pin(data.pin)
    token = create_session_token()
    set_session_cookie(response, token)
    return {"ok": True}


@router.get("/api/bootstrap")
def bootstrap(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    app_settings = load_app_settings()
    return {
        "ok": True,
        "character_catalog_root": str(CHARACTER_CATALOG_ROOT),
        "character_select_settings": settings,
        "anima_workflow": str(ANIMA_WORKFLOW_PATH),
        "anima_mapping": str(ANIMA_MAPPING_PATH),
        "catalog_count": len(catalog.wai),
        "custom_count": len(catalog.custom),
        "original_count": len(catalog.original),
        "settings": app_settings,
        "anima_shift": anima_shift_capability(),
        "negative_presets": NEGATIVE_PRESETS,
        "defaults": {
            "api_addr": settings.get("api_addr") or COMFYUI_ADDR_DEFAULT,
            "workflow_mode": app_settings.get("workflow_mode", "anima"),
            "common_prompt": app_settings.get("default_common_prompt", ""),
            "positive_prompt": app_settings.get("default_positive_prompt", ""),
            "negative_prompt": app_settings.get("default_negative_prompt", ""),
            "negative_prompt_mode": app_settings.get("negative_prompt_mode", "append"),
            "width": app_settings.get("width", settings.get("width", 1024)),
            "height": app_settings.get("height", 1536),
            "steps": app_settings.get("steps", 32),
            "cfg": app_settings.get("cfg", 4.5),
            "shift": app_settings.get("shift", anima_shift_capability().get("default", 4.0)),
            "sampler": app_settings.get("sampler", "er_sde"),
            "scheduler": app_settings.get("scheduler", "simple"),
            "seed": app_settings.get("seed", settings.get("random_seed", -1)),
            "model": app_settings.get("model", "Anima\\anima-preview3-base.safetensors"),
            "text_encoder": app_settings.get("text_encoder", "qwen_3_06b_base.safetensors"),
            "vae": app_settings.get("vae", "qwen_image_vae.safetensors"),
        },
    }
