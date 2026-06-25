from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock, Thread
from typing import Any
import uuid

from .history_store import copy_public_image, load_history_item, public_save_cached_info, public_save_settings_hash

_LOCK = RLock()
_JOBS: dict[str, dict[str, Any]] = {}
_LATEST_BY_HISTORY: dict[str, str] = {}
_JOB_TTL = timedelta(hours=2)
_PUBLIC_SAVE_RESPONSE_KEYS = {
    "saved",
    "url",
    "filename",
    "created_at",
    "updated_at",
    "cached",
    "size_bytes",
    "width",
    "height",
    "watermark_text",
    "watermark_position",
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _public_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    allowed = {
        "job_id",
        "status",
        "history_id",
        "created_at",
        "started_at",
        "finished_at",
        "public_image_url",
        "public_save",
        "message",
        "error",
    }
    result = {key: job.get(key) for key in allowed if key in job}
    if isinstance(result.get("public_save"), dict):
        result["public_save"] = _safe_public_save(result["public_save"])
    return result


def _safe_public_save(public_save: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(public_save, dict):
        return {}
    return {key: public_save.get(key) for key in _PUBLIC_SAVE_RESPONSE_KEYS if key in public_save}


def _cleanup_locked() -> None:
    now = datetime.now()
    for job_id, job in list(_JOBS.items()):
        finished_dt = job.get("finished_dt")
        if isinstance(finished_dt, datetime) and now - finished_dt > _JOB_TTL:
            _JOBS.pop(job_id, None)
            if _LATEST_BY_HISTORY.get(str(job.get("history_id") or "")) == job_id:
                _LATEST_BY_HISTORY.pop(str(job.get("history_id") or ""), None)


def _settings_hash(item: dict[str, Any], watermark: dict[str, Any]) -> str:
    source = Path(str(item.get("image_path") or ""))
    apply_watermark = bool(watermark and watermark.get("enabled", False))
    return public_save_settings_hash(source, apply_watermark, watermark)


def _active_job_locked(history_id: str) -> dict[str, Any] | None:
    job_id = _LATEST_BY_HISTORY.get(history_id)
    job = _JOBS.get(job_id or "")
    if job and job.get("status") in {"queued", "running"}:
        return job
    return None


def _mark(job_id: str, **patch: Any) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return {}
        job.update(patch)
        if patch.get("finished_at"):
            job["finished_dt"] = datetime.now()
        return _public_job(job) or {}


def _done_response(history_id: str, public_save: dict[str, Any], *, message: str = "done") -> dict[str, Any]:
    item = load_history_item(history_id) or {}
    safe_public_save = _safe_public_save(public_save)
    public_image_url = item.get("public_image_url") or safe_public_save.get("url")
    return {
        "ok": True,
        "queued": False,
        "status": "done",
        "history_id": history_id,
        "public_image_url": public_image_url,
        "public_save": safe_public_save,
        "filename": safe_public_save.get("filename") or f"{history_id}_public.png",
        "message": message,
    }


def _run_public_save_job(job_id: str, history_id: str, item: dict[str, Any], watermark: dict[str, Any]) -> None:
    _mark(job_id, status="running", started_at=_now_iso(), message="saving")
    try:
        public_save = copy_public_image(dict(item), watermark)
        current = load_history_item(history_id) or item
        public_image_url = current.get("public_image_url") or public_save.get("url")
        _mark(
            job_id,
            status="done",
            finished_at=_now_iso(),
            public_image_url=public_image_url,
            public_save=public_save,
            item=current,
            message="cached" if public_save.get("cached") else "saved",
        )
    except Exception:
        _mark(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            message="public save failed",
            error="public save failed",
        )


def start_public_save_job(history_id: str, item: dict[str, Any], watermark: dict[str, Any]) -> dict[str, Any]:
    cached = public_save_cached_info(item, watermark)
    if cached:
        return _done_response(history_id, cached, message="cached")
    settings_hash = _settings_hash(item, watermark)
    with _LOCK:
        _cleanup_locked()
        active = _active_job_locked(history_id)
        if active:
            if active.get("settings_hash") != settings_hash:
                return {
                    "ok": False,
                    "queued": False,
                    "status": "conflict",
                    "history_id": history_id,
                    "message": "public save already running with different settings",
                    "job": _public_job(active),
                }
            return {
                "ok": True,
                "queued": False,
                "job_id": active["job_id"],
                "status": active["status"],
                "history_id": history_id,
                "message": "public save already running",
                "job": _public_job(active),
            }
        job_id = f"public-save-{uuid.uuid4().hex[:12]}"
        job = {
            "job_id": job_id,
            "status": "queued",
            "history_id": history_id,
            "created_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
            "public_image_url": "",
            "public_save": {},
            "settings_hash": settings_hash,
            "message": "queued",
            "error": "",
        }
        _JOBS[job_id] = job
        _LATEST_BY_HISTORY[history_id] = job_id
    thread = Thread(target=_run_public_save_job, args=(job_id, history_id, dict(item), dict(watermark or {})), daemon=True)
    thread.start()
    return {
        "ok": True,
        "queued": True,
        "job_id": job_id,
        "status": "queued",
        "history_id": history_id,
        "message": "public save queued",
        "job": _public_job(job),
    }


def public_save_status(history_id: str, job_id: str | None = None) -> dict[str, Any]:
    with _LOCK:
        _cleanup_locked()
        resolved_job_id = str(job_id or _LATEST_BY_HISTORY.get(history_id) or "")
        raw_job = _JOBS.get(resolved_job_id)
        if job_id and not raw_job:
            return {
                "ok": False,
                "queued": False,
                "status": "not_found",
                "history_id": history_id,
                "message": "public save job not found",
            }
        if raw_job and str(raw_job.get("history_id") or "") != str(history_id):
            return {
                "ok": False,
                "queued": False,
                "status": "not_found",
                "history_id": history_id,
                "message": "public save job not found",
            }
        job = _public_job(raw_job)
    if job:
        public_save = job.get("public_save") or {}
        response = {
            "ok": True,
            "queued": job.get("status") in {"queued", "running"},
            "job_id": job.get("job_id"),
            "status": job.get("status"),
            "history_id": history_id,
            "public_image_url": job.get("public_image_url") or "",
            "public_save": public_save,
            "filename": public_save.get("filename") or f"{history_id}_public.png",
            "message": job.get("message") or "",
            "job": job,
        }
        if job.get("error"):
            response["error"] = job.get("error")
        return response
    item = load_history_item(history_id) or {}
    public_save = item.get("public_save") if isinstance(item.get("public_save"), dict) else {}
    if public_save.get("saved"):
        return _done_response(history_id, public_save, message="done")
    return {
        "ok": True,
        "queued": False,
        "status": "missing",
        "history_id": history_id,
        "public_image_url": "",
        "public_save": {},
        "message": "no public save job",
    }


def _reset_public_save_jobs_for_tests() -> None:
    with _LOCK:
        _JOBS.clear()
        _LATEST_BY_HISTORY.clear()
