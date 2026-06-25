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
from .config import COMFYUI_ADDR_DEFAULT, USER_DATA_DIR
from .comfyui_restart_config import (
    LOCAL_RESTART_CONFIG_PATH,
    load_local_restart_config,
    local_restart_command,
    validate_local_restart_config,
)

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
    timeout = _float_env("COMFYUI_RESTART_TIMEOUT_SECONDS", 180.0, 1.0)
    interval = _float_env("COMFYUI_RESTART_POLL_INTERVAL_SECONDS", 3.0, 0.2)
    if command:
        enabled = _bool_env("LUNA_COMFY_RESTART_ENABLED") and bool(command)
        return {
            "enabled": enabled,
            "configured": bool(command),
            "command": command,
            "command_label": _command_label(command),
            "timeout_seconds": timeout,
            "poll_interval_seconds": interval,
            "cwd": str(os.environ.get("COMFYUI_RESTART_CWD", "") or "").strip(),
            "shell": _bool_env("COMFYUI_RESTART_SHELL"),
            "source": "environment",
            "message": "",
        }

    local_path = Path(os.environ.get("COMFYUI_RESTART_CONFIG_PATH") or LOCAL_RESTART_CONFIG_PATH)
    local_config = None
    try:
        local_config = load_local_restart_config(local_path)
    except Exception:
        local_config = {}
    if local_config is not None:
        normalized, errors = validate_local_restart_config(local_config)
        enabled = bool(normalized.get("enabled")) and not errors
        return {
            "enabled": enabled,
            "configured": True,
            "command": local_restart_command(local_path),
            "command_label": "configured",
            "timeout_seconds": float(normalized.get("startup_timeout_seconds") or timeout),
            "poll_interval_seconds": float(normalized.get("poll_interval_seconds") or interval),
            "cwd": str(os.environ.get("COMFYUI_RESTART_CWD", "") or "").strip(),
            "shell": False,
            "source": "local",
            "message": "local restart config invalid" if errors else "",
        }

    return {
        "enabled": False,
        "configured": False,
        "command": "",
        "command_label": "",
        "timeout_seconds": timeout,
        "poll_interval_seconds": interval,
        "cwd": str(os.environ.get("COMFYUI_RESTART_CWD", "") or "").strip(),
        "shell": _bool_env("COMFYUI_RESTART_SHELL"),
        "source": "disabled",
        "message": "",
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
        "old_pid",
        "new_pid",
        "stage",
        "duration_ms",
        "log_available",
    }
    return {key: job.get(key) for key in allowed if key in job}


def _cleanup_locked() -> None:
    now = datetime.now()
    for job_id, job in list(_JOBS.items()):
        finished_at = job.get("finished_dt")
        if isinstance(finished_at, datetime) and now - finished_at > _JOB_TTL:
            _JOBS.pop(job_id, None)


def restart_capability() -> dict[str, Any]:
    _reconcile_last_job()
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
        "message": cfg.get("message", ""),
        "last_job": last_job,
    }


def latest_restart_status() -> dict[str, Any]:
    _reconcile_last_job()
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


def _args_with_status_file(args: list[str], status_path: Path) -> list[str]:
    lowered = [str(arg).lower() for arg in args]
    if any("restart_comfyui_windows.ps1" in arg for arg in lowered) and "-statusfile" not in lowered:
        return [*args, "-StatusFile", str(status_path)]
    return args


def _is_windows_restart_wrapper(args: list[str]) -> bool:
    return any("restart_comfyui_windows.ps1" in str(arg).lower() for arg in args)


def _read_tail_file(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    try:
        return _tail(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return ""


def _mark(job_id: str, **patch: Any) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return {}
        if patch.get("finished_at") and job.get("started_monotonic") is not None:
            patch.setdefault("duration_ms", int((time.monotonic() - float(job["started_monotonic"])) * 1000))
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


def _queue_restart_safety(addr: str) -> dict[str, Any]:
    try:
        queue = comfy_client.queue_info(addr)
    except Exception:
        return {
            "ok": False,
            "busy": True,
            "status": "queue_unavailable",
            "message": "Could not inspect ComfyUI queue; restart refused.",
        }
    running = queue.get("queue_running") or []
    pending = queue.get("queue_pending") or []
    if running or pending:
        return {
            "ok": False,
            "busy": True,
            "status": "busy",
            "message": "ComfyUI queue is not empty; restart refused.",
            "running_count": len(running) if isinstance(running, list) else 1,
            "pending_count": len(pending) if isinstance(pending, list) else 1,
        }
    return {"ok": True, "busy": False, "status": "idle", "message": "ComfyUI queue is empty."}


def _parse_restart_output(stdout: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for line in str(stdout or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower().lstrip("\ufeff")
        value = value.strip()
        if key in {"old_pid", "new_pid"}:
            try:
                parsed[key] = int(value)
            except ValueError:
                continue
        elif key == "log_available":
            parsed[key] = value.lower() in _TRUTHY
        elif key == "stage" and value:
            parsed[key] = value[:40]
    return parsed


def _job_status_path(job_id: str) -> Path:
    return USER_DATA_DIR / "logs" / "comfyui_restart_jobs" / f"{job_id}.status.txt"


def _reconcile_restart_job(job_id: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.get("status") not in {"queued", "running", "waiting_for_comfy"}:
            return
        timeout = float(job.get("timeout_seconds") or 180.0)
        started_monotonic = float(job.get("started_monotonic") or time.monotonic())
    expired = time.monotonic() - started_monotonic > timeout
    fields = _parse_restart_output(_read_tail_file(_job_status_path(job_id)))
    safe_fields = {key: value for key, value in fields.items() if key != "stage"}
    if fields:
        _mark(job_id, **fields)
    if expired:
        _mark(
            job_id,
            status="failed",
            stage="failed",
            finished_at=_now_iso(),
            comfy_reachable=False,
            message="timed out waiting for ComfyUI" if fields.get("new_pid") else "restart command timed out",
            **safe_fields,
        )
        return
    if fields.get("new_pid"):
        settings = load_settings()
        addr = str(settings.get("api_addr") or COMFYUI_ADDR_DEFAULT)
        if _comfy_ready(addr):
            _mark(
                job_id,
                status="ready",
                stage="ready",
                exit_code=0,
                finished_at=_now_iso(),
                comfy_reachable=True,
                message="ComfyUI is reachable",
                **safe_fields,
            )
            return
        _mark(job_id, status="waiting_for_comfy", stage="waiting_for_comfy", message="waiting for ComfyUI", **safe_fields)


def _reconcile_last_job() -> None:
    with _LOCK:
        job_id = _LAST_JOB_ID
    if job_id:
        _reconcile_restart_job(job_id)


def _run_restart_job(job_id: str, cfg: dict[str, Any], addr: str) -> None:
    started = _now_iso()
    _mark(job_id, status="running", stage="validating", started_at=started, message="restart command running")
    command = str(cfg.get("command") or "")
    cwd = str(cfg.get("cwd") or "").strip() or None
    timeout = float(cfg.get("timeout_seconds") or 180.0)
    job_log_dir = USER_DATA_DIR / "logs" / "comfyui_restart_jobs"
    job_log_dir.mkdir(parents=True, exist_ok=True)
    status_path = job_log_dir / f"{job_id}.status.txt"
    stdout_path = job_log_dir / f"{job_id}.stdout.txt"
    stderr_path = job_log_dir / f"{job_id}.stderr.txt"
    try:
        if cfg.get("shell"):
            with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, stderr_path.open("w", encoding="utf-8", errors="replace") as stderr_handle:
                completed = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    timeout=timeout,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                    check=False,
                )
            stdout_tail = _read_tail_file(stdout_path)
            stderr_tail = _read_tail_file(stderr_path)
        else:
            command_args = _args_with_status_file(_args_for_command(command), status_path)
            if _is_windows_restart_wrapper(command_args):
                creationflags = (
                    getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
                subprocess.Popen(
                    command_args,
                    shell=False,
                    cwd=cwd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    creationflags=creationflags,
                )
                _mark(job_id, status="running", stage="stopping", message="restart command running")
                return
            else:
                with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, stderr_path.open("w", encoding="utf-8", errors="replace") as stderr_handle:
                    completed = subprocess.run(
                        command_args,
                        shell=False,
                        cwd=cwd,
                        timeout=timeout,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        text=True,
                        check=False,
                    )
                stdout_tail = _read_tail_file(stdout_path)
                stderr_tail = _read_tail_file(stderr_path)
    except subprocess.TimeoutExpired as exc:
        stdout_tail = _read_tail_file(stdout_path) or _tail(exc.stdout)
        stderr_tail = _read_tail_file(stderr_path) or _tail(exc.stderr)
        _mark(
            job_id,
            status="failed",
            stage="failed",
            finished_at=_now_iso(),
            exit_code=None,
            comfy_reachable=False,
            message="restart command timed out",
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
        )
        return
    except Exception:
        _mark(
            job_id,
            status="failed",
            stage="failed",
            finished_at=_now_iso(),
            exit_code=None,
            comfy_reachable=False,
            message="restart command failed",
            stdout_tail="",
            stderr_tail="",
        )
        return

    wrapper_fields = _parse_restart_output(stdout_tail)
    if completed.returncode != 0:
        _mark(
            job_id,
            status="failed",
            stage="failed",
            finished_at=_now_iso(),
            exit_code=completed.returncode,
            comfy_reachable=False,
            message=f"restart command exited with {completed.returncode}",
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            **wrapper_fields,
        )
        return

    _mark(
        job_id,
        status="waiting_for_comfy",
        stage="waiting_for_comfy",
        exit_code=completed.returncode,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
        message="waiting for ComfyUI",
        **wrapper_fields,
    )
    deadline = time.time() + timeout
    interval = float(cfg.get("poll_interval_seconds") or 3.0)
    while time.time() < deadline:
        if _comfy_ready(addr):
            _mark(
                job_id,
                status="ready",
                stage="ready",
                finished_at=_now_iso(),
                comfy_reachable=True,
                message="ComfyUI is reachable",
            )
            return
        time.sleep(interval)
    _mark(
        job_id,
        status="failed",
        stage="failed",
        finished_at=_now_iso(),
        comfy_reachable=False,
        message="timed out waiting for ComfyUI",
    )


def start_restart() -> dict[str, Any]:
    _reconcile_last_job()
    cfg = restart_config()
    if not cfg["enabled"]:
        return {
            "ok": False,
            "queued": False,
            "status": "disabled",
            "message": cfg.get("message") or "ComfyUI restart is disabled. Set LUNA_COMFY_RESTART_ENABLED=1 and COMFYUI_RESTART_COMMAND on the server.",
            "capability": restart_capability(),
        }
    settings = load_settings()
    addr = str(settings.get("api_addr") or COMFYUI_ADDR_DEFAULT)
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

    safety = _queue_restart_safety(addr)
    if not safety.get("ok"):
        return {
            "ok": False,
            "queued": False,
            "status": safety.get("status", "busy"),
            "message": safety.get("message", "ComfyUI restart refused."),
            "queue": {key: safety.get(key) for key in ("running_count", "pending_count") if key in safety},
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
        job_id = f"comfy-restart-{uuid.uuid4().hex[:12]}"
        job = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "started_at": None,
            "finished_at": None,
            "started_monotonic": time.monotonic(),
            "exit_code": None,
            "comfy_reachable": False,
            "message": "queued",
            "stdout_tail": "",
            "stderr_tail": "",
            "command_label": cfg["command_label"],
            "timeout_seconds": cfg["timeout_seconds"],
            "old_pid": None,
            "new_pid": None,
            "log_available": False,
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
