from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .schemas.history import PublicSaveRequest
from .settings_store import load_app_settings


class CachedStaticFiles(StaticFiles):
    def file_response(self, full_path: Any, stat_result: Any, scope: Any, status_code: int = 200) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def cached_file_response(path: Path, media_type: str | None = None) -> FileResponse:
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=604800, immutable"},
    )


def resolve_public_save_watermark(data: PublicSaveRequest, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if data.watermark_client == "current":
        watermark = dict(data.watermark) if data.apply_watermark else {"enabled": False}
        watermark["enabled"] = data.apply_watermark
        return watermark
    if data.apply_watermark:
        watermark = dict(data.watermark)
        watermark["enabled"] = True
        return watermark
    app_settings = settings if settings is not None else load_app_settings()
    configured = dict(app_settings.get("watermark") or {})
    public_save_settings = app_settings.get("public_save") if isinstance(app_settings.get("public_save"), dict) else {}
    configured["enabled"] = bool(public_save_settings.get("apply_watermark", configured.get("enabled", False)))
    return configured
