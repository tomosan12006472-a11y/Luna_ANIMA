from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import shlex
import subprocess
from threading import RLock, Thread
import time
from typing import Any
import uuid

from . import comfy_client
from .anima_adapter import load_settings
from .config import COMFYUI_ADDR_DEFAULT

_TRUTHY = {"1", "true", "yes", "on"}
_TAIL_LIMIT = 4096
_JOB_TTL = timedelta(hours=2)
_LOCK = RLock()
_JOBS: dict[str, dict[str, Any]] = {}
_LAST_JOB_ID: str | None = None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _float_env(name: str, default: float, minimum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in _TRUTHY


def _tail(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value or "")
    if len(text) <= _TAIL_LIMIT:
        return text
    return text[-_TAIL_LIMIT:]


def _command_label(command: str) -> str:
    if not command.strip():
        return ""
    return "configured"


def restart_config() -> dict[str, Any]:
    command = str(os.environ.get("COMFYUI_RESTART_COMMAND", "") or "").strip()
    enabled = _bool_env("LUNA_COMFY_RESTART_ENABLED") and bool(command)
    timeout = _float_env("COMFYUI_RESTART_TIMEOUT_SECONDS", 180.0, 1.0)
    interval = _float_env("COMFYUI_RESTART_POLL_INTERVAL_SECONDS", 3.0, 0.2)
    return {
        "enabled": enabled,
        "configured": bool(command),
        "command": command,
        "command_label": _command_label(command),
        "timeout_seconds": timeout,
        "poll_interval_seconds": interval,
        "cwd": str(os.environ.get("COMFYUI_RESTART_CWD", "") or "").strip(),
        "shell": _bool_env("COMFYUI_RESTART_SHELL"),
    }


def _public_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    allowed = {
        "job_id",
        "status",
        "started_at",
        "finished_at",
        "exit_code",
        "comfy_reachable",
        "message",
        "command_label",
    }
    return {key: job.get(key) for key in allowed if key in job}


def _cleanup_locked() -> None:
    now = datetime.now()
    for job_id, job in list(_JOBS.items()):
        finished_at = job.get("finished_dt")
        if isinstance(finished_at, datetime) and now - finished_at > _JOB_TTL:
            _JOBS.pop(job_id, None)


def restart_capability() -> dict[str, Any]:
    cfg = restart_config()
    with _LOCK:
        _cleanup_locked()
        last_job = _public_job(_JOBS.get(_LAST_JOB_ID or ""))
    return {
        "ok": True,
        "enabled": cfg["enabled"],
        "configured": cfg["configured"],
        "command_label": cfg["command_label"],
        "timeout_seconds": cfg["timeout_seconds"],
        "poll_interval_seconds": cfg["poll_interval_seconds"],
        "last_job": last_job,
    }


def latest_restart_status() -> dict[str, Any]:
    with _LOCK:
        _cleanup_locked()
        job = _public_job(_JOBS.get(_LAST_JOB_ID or ""))
    return {"ok": True, "job": job}


def _active_job_locked() -> dict[str, Any] | None:
    for job in _JOBS.values():
        if job.get("status") in {"queued", "running", "waiting_for_comfy"}:
            return job
    return None


def _args_for_command(command: str) -> list[str]:
    args = [arg.strip('"') for arg in shlex.split(command, posix=os.name != "nt")]
    if os.name == "nt" and args:
        suffix = Path(args[0].strip('"')).suffix.lower()
        if suffix in {".bat", ".cmd"}:
            return ["cmd", "/c", *args]
    return args


def _mark(job_id: str, **patch: Any) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS[job_id]
        job.update(patch)
        if patch.get("finished_at"):
            job["finished_dt"] = datetime.now()
        return _public_job(job) or {}


def _comfy_ready(addr: str) -> bool:
    try:
        info = comfy_client.object_info(addr)
    except Exception:
        return False
    return isinstance(info, dict) and bool(info)


def _run_restart_job(job_id: str, cfg: dict[str, Any], addr: str) -> None:
    started = _now_iso()
    _mark(job_id, status="running", started_at=started, message="restart command running")
    command = str(cfg.get("command") or "")
    cwd = str(cfg.get("cwd") or "").strip() or None
    timeout = float(cfg.get("timeout_seconds") or 180.0)
    try:
        if cfg.get("shell"):
            completed = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                timeout=timeout,
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            completed = subprocess.run(
                _args_for_command(command),
                shell=False,
                cwd=cwd,
                timeout=timeout,
                capture_output=True,
                text=True,
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        _mark(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            exit_code=None,
            comfy_reachable=False,
            message="restart command timed out",
            stdout_tail=_tail(exc.stdout),
            stderr_tail=_tail(exc.stderr),
        )
        return
    except Exception:
        _mark(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            exit_code=None,
            comfy_reachable=False,
            message="restart command failed",
            stdout_tail="",
            stderr_tail="",
        )
        return

    stdout_tail = _tail(completed.stdout)
    stderr_tail = _tail(completed.stderr)
    if completed.returncode != 0:
        _mark(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            exit_code=completed.returncode,
            comfy_reachable=False,
            message=f"restart command exited with {completed.returncode}",
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
        )
        return

    _mark(
        job_id,
        status="waiting_for_comfy",
        exit_code=completed.returncode,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
        message="waiting for ComfyUI",
    )
    deadline = time.time() + timeout
    interval = float(cfg.get("poll_interval_seconds") or 3.0)
    while time.time() < deadline:
        if _comfy_ready(addr):
            _mark(
                job_id,
                status="ready",
                finished_at=_now_iso(),
                comfy_reachable=True,
                message="ComfyUI is reachable",
            )
            return
        time.sleep(interval)
    _mark(
        job_id,
        status="failed",
        finished_at=_now_iso(),
        comfy_reachable=False,
        message="timed out waiting for ComfyUI",
    )


def start_restart() -> dict[str, Any]:
    cfg = restart_config()
    if not cfg["enabled"]:
        return {
            "ok": False,
            "queued": False,
            "status": "disabled",
            "message": "ComfyUI restart is disabled. Set LUNA_COMFY_RESTART_ENABLED=1 and COMFYUI_RESTART_COMMAND on the server.",
            "capability": restart_capability(),
        }
    with _LOCK:
        _cleanup_locked()
        active = _active_job_locked()
        if active:
            return {
                "ok": True,
                "queued": False,
                "job_id": active["job_id"],
                "status": active["status"],
                "message": "restart already running",
                "job": _public_job(active),
            }
        settings = load_settings()
        addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
        job_id = f"comfy-restart-{uuid.uuid4().hex[:12]}"
        job = {
            "job_id": job_id,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "comfy_reachable": False,
            "message": "queued",
            "stdout_tail": "",
            "stderr_tail": "",
            "command_label": cfg["command_label"],
        }
        _JOBS[job_id] = job
        global _LAST_JOB_ID
        _LAST_JOB_ID = job_id
    thread = Thread(target=_run_restart_job, args=(job_id, cfg, str(addr)), daemon=True)
    thread.start()
    return {
        "ok": True,
        "queued": True,
        "job_id": job_id,
        "status": "queued",
        "message": "restart queued",
        "job": _public_job(job),
    }


def _reset_restart_jobs_for_tests() -> None:
    global _LAST_JOB_ID
    with _LOCK:
        _JOBS.clear()
        _LAST_JOB_ID = None
