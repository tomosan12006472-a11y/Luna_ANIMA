from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import ROOT_DIR, USER_DATA_DIR


LOCAL_RESTART_CONFIG_PATH = USER_DATA_DIR / "comfyui_restart.local.json"
LOCAL_RESTART_ENV_PATH = USER_DATA_DIR / "comfyui_restart_env.bat"
WINDOWS_RESTART_WRAPPER_PATH = ROOT_DIR / "scripts" / "restart_comfyui_windows.ps1"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_path(value: Any) -> Path | None:
    text = _clean_text(value)
    if not text:
        return None
    return Path(text).expanduser()


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except Exception:
        return False
    return True


def _int_range(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def load_local_restart_config(path: Path | str | None = None) -> dict[str, Any] | None:
    config_path = Path(path) if path else LOCAL_RESTART_CONFIG_PATH
    if not config_path.exists():
        return None
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def validate_local_restart_config(data: dict[str, Any] | None, *, require_exists: bool = True) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    raw = data if isinstance(data, dict) else {}
    enabled = bool(raw.get("enabled"))
    mode = _clean_text(raw.get("mode") or "windows_wrapper")
    if mode != "windows_wrapper":
        errors.append("mode must be windows_wrapper")

    comfyui_root = _clean_path(raw.get("comfyui_root"))
    python_executable = _clean_path(raw.get("python_executable"))
    main_script = _clean_path(raw.get("main_script"))
    cwd = _clean_path(raw.get("cwd")) or comfyui_root
    log_dir = _clean_path(raw.get("log_dir")) or (USER_DATA_DIR / "logs" / "comfyui_restart")
    args_raw = raw.get("args")
    args = [str(item) for item in args_raw] if isinstance(args_raw, list) else []

    for label, path, kind in (
        ("comfyui_root", comfyui_root, "dir"),
        ("python_executable", python_executable, "file"),
        ("main_script", main_script, "file"),
        ("cwd", cwd, "dir"),
    ):
        if path is None:
            errors.append(f"{label} is required")
            continue
        if not require_exists:
            continue
        if kind == "dir" and not path.is_dir():
            errors.append(f"{label} does not exist")
        if kind == "file" and not path.is_file():
            errors.append(f"{label} does not exist")

    if not args:
        errors.append("args must be a non-empty list")
    elif main_script is not None:
        first = Path(args[0].strip('"')) if args[0] else Path("")
        if first.name.lower() != main_script.name.lower() and str(main_script) not in args[0]:
            errors.append("args must start with the configured main_script")

    if comfyui_root is not None and main_script is not None and not _is_relative_to(main_script, comfyui_root):
        errors.append("main_script must be under comfyui_root")
    if comfyui_root is not None and cwd is not None and not _is_relative_to(cwd, comfyui_root):
        errors.append("cwd must be under comfyui_root")

    port = _int_range(raw.get("port"), 8188, 1, 65535)
    stop_timeout = _int_range(raw.get("stop_timeout_seconds"), 15, 1, 120)
    startup_timeout = _int_range(raw.get("startup_timeout_seconds"), 180, 1, 900)

    normalized = {
        "schema_version": 1,
        "enabled": enabled,
        "mode": mode,
        "comfyui_root": str(comfyui_root) if comfyui_root else "",
        "python_executable": str(python_executable) if python_executable else "",
        "main_script": str(main_script) if main_script else "",
        "cwd": str(cwd) if cwd else "",
        "args": args,
        "host": _clean_text(raw.get("host") or "127.0.0.1"),
        "port": port,
        "stop_timeout_seconds": stop_timeout,
        "startup_timeout_seconds": startup_timeout,
        "poll_interval_seconds": _int_range(raw.get("poll_interval_seconds"), 3, 1, 60),
        "log_dir": str(log_dir),
    }
    return normalized, errors


def local_restart_command_args(config_path: Path | str | None = None) -> list[str]:
    path = Path(config_path) if config_path else LOCAL_RESTART_CONFIG_PATH
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(WINDOWS_RESTART_WRAPPER_PATH),
        "-Config",
        str(path),
    ]


def local_restart_command(config_path: Path | str | None = None) -> str:
    return subprocess.list2cmdline(local_restart_command_args(config_path))


def local_restart_env_lines(config_path: Path | str | None = None) -> list[str]:
    path = Path(config_path) if config_path else LOCAL_RESTART_CONFIG_PATH
    return [
        "@echo off",
        "rem Machine-local ComfyUI restart settings generated by scripts\\configure_comfyui_restart.py",
        "rem The JSON file is the source of truth; set enabled=false there to disable restart.",
        f'set "COMFYUI_RESTART_CONFIG_PATH={path}"',
    ]
