from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.request
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.comfyui_restart_config import (  # noqa: E402
    LOCAL_RESTART_CONFIG_PATH,
    LOCAL_RESTART_ENV_PATH,
    local_restart_env_lines,
    validate_local_restart_config,
)


def parse_addr(value: str | None) -> tuple[str, int]:
    raw = str(value or "").strip() or "127.0.0.1:8188"
    if raw.startswith("http://"):
        raw = raw[7:]
    if raw.startswith("https://"):
        raw = raw[8:]
    raw = raw.rstrip("/")
    if ":" not in raw:
        return raw, 8188
    host, port_text = raw.rsplit(":", 1)
    try:
        port = int(port_text)
    except ValueError:
        port = 8188
    return host or "127.0.0.1", port


def configured_addr() -> tuple[str, int]:
    settings_path = ROOT_DIR / "user_data" / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            addr = data.get("api_addr") if isinstance(data, dict) else None
            if addr:
                return parse_addr(str(addr))
        except Exception:
            pass
    return parse_addr(os.environ.get("COMFYUI_ADDR") or "127.0.0.1:8188")


def powershell_json(script: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "PowerShell detection failed").strip())
    text = completed.stdout.strip()
    return json.loads(text) if text else {}


def listener_process(port: int) -> dict[str, Any]:
    script = f"""
$conn = Get-NetTCPConnection -State Listen -LocalPort {int(port)} -ErrorAction Stop | Select-Object -First 1
$proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)"
$parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)"
[pscustomobject]@{{
  local_address = $conn.LocalAddress
  local_port = $conn.LocalPort
  owning_process = $conn.OwningProcess
  process = [pscustomobject]@{{
    process_id = $proc.ProcessId
    parent_process_id = $proc.ParentProcessId
    name = $proc.Name
    executable_path = $proc.ExecutablePath
    command_line = $proc.CommandLine
    creation_date = $proc.CreationDate
  }}
  parent = [pscustomobject]@{{
    process_id = $parent.ProcessId
    parent_process_id = $parent.ParentProcessId
    name = $parent.Name
    executable_path = $parent.ExecutablePath
    command_line = $parent.CommandLine
    creation_date = $parent.CreationDate
  }}
}} | ConvertTo-Json -Depth 6
"""
    return powershell_json(script)


def http_json(url: str, timeout: float = 8.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def split_windows_command_line(command_line: str) -> list[str]:
    return [part.strip('"') for part in shlex.split(str(command_line or ""), posix=False)]


def find_main_script(argv: list[str], command_line_parts: list[str]) -> Path | None:
    for part in [*argv, *command_line_parts]:
        cleaned = str(part or "").strip('"')
        if cleaned.lower().endswith("main.py") and "comfyui" in cleaned.lower():
            return Path(cleaned)
    return None


def comfy_root_for_main(main_script: Path) -> Path:
    parent = main_script.parent
    if parent.name.lower() == "comfyui":
        return parent.parent
    return parent


def derive_args(argv: list[str], command_line_parts: list[str], main_script: Path) -> list[str]:
    if argv:
        return [str(item) for item in argv]
    for index, part in enumerate(command_line_parts):
        if Path(str(part).strip('"')).name.lower() == main_script.name.lower():
            return [str(item).strip('"') for item in command_line_parts[index:]]
    return [str(main_script)]


def detect_config() -> tuple[dict[str, Any], dict[str, Any]]:
    host, port = configured_addr()
    process_data = listener_process(port)
    system_stats = http_json(f"http://{host}:{port}/system_stats")
    argv = [str(item) for item in system_stats.get("system", {}).get("argv", []) if item]
    process = process_data.get("process") or {}
    parent = process_data.get("parent") or {}
    command_parts = split_windows_command_line(str(process.get("command_line") or ""))
    main_script = find_main_script(argv, command_parts)
    if main_script is None:
        raise RuntimeError("Could not find ComfyUI main.py in the listener command line or /system_stats argv.")
    comfy_root = comfy_root_for_main(main_script)
    args = derive_args(argv, command_parts, main_script)

    parent_command = str(parent.get("command_line") or "")
    if str(main_script).lower() in parent_command.lower() and parent.get("executable_path"):
        python_executable = Path(str(parent["executable_path"]))
    else:
        python_executable = Path(str(process.get("executable_path") or ""))

    config = {
        "schema_version": 1,
        "enabled": True,
        "mode": "windows_wrapper",
        "comfyui_root": str(comfy_root),
        "python_executable": str(python_executable),
        "main_script": str(main_script),
        "cwd": str(comfy_root),
        "args": args,
        "host": host,
        "port": port,
        "stop_timeout_seconds": 15,
        "startup_timeout_seconds": 180,
        "poll_interval_seconds": 3,
        "log_dir": str(ROOT_DIR / "user_data" / "logs" / "comfyui_restart"),
    }
    evidence = {
        "listener": {
            "pid": process_data.get("owning_process"),
            "local_address": process_data.get("local_address"),
            "port": process_data.get("local_port"),
        },
        "process": process,
        "parent": parent,
        "system_stats_argv": argv,
    }
    return config, evidence


def queue_is_empty(host: str, port: int) -> bool:
    queue = http_json(f"http://{host}:{port}/queue", timeout=5.0)
    return not queue.get("queue_running") and not queue.get("queue_pending")


def write_local_files(config: dict[str, Any]) -> None:
    LOCAL_RESTART_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_RESTART_CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOCAL_RESTART_ENV_PATH.write_text("\n".join(local_restart_env_lines(LOCAL_RESTART_CONFIG_PATH)) + "\n", encoding="utf-8")


def run_wrapper_test(config_path: Path, host: str, port: int) -> None:
    if not queue_is_empty(host, port):
        raise RuntimeError("ComfyUI queue is not empty; refusing to restart.")
    status_path = ROOT_DIR / "user_data" / "logs" / "comfyui_restart_jobs" / "configure_comfyui_restart_test.status.txt"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text("", encoding="utf-8")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT_DIR / "scripts" / "restart_comfyui_windows.ps1"),
        "-Config",
        str(config_path),
        "-StatusFile",
        str(status_path),
    ]
    process = subprocess.Popen(command, cwd=str(ROOT_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 60
    while time.time() < deadline:
        status = status_path.read_text(encoding="utf-8", errors="replace")
        if "new_pid=" in status:
            break
        if process.poll() not in (None, 0):
            raise RuntimeError("restart wrapper failed")
        time.sleep(0.5)
    else:
        raise RuntimeError("Timed out waiting for restart wrapper to start ComfyUI.")
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            info = http_json(f"http://{host}:{port}/object_info", timeout=5.0)
            if info:
                print("ComfyUI object_info is reachable.")
                return
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError("Timed out waiting for ComfyUI object_info after restart.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect and configure local ComfyUI restart settings for Luna ANIMA.")
    parser.add_argument("--detect", action="store_true", help="detect the current ComfyUI listener and print the launch spec")
    parser.add_argument("--write", action="store_true", help="write user_data/comfyui_restart.local.json and comfyui_restart_env.bat")
    parser.add_argument("--dry-run", action="store_true", help="print detected config without writing")
    parser.add_argument("--test", action="store_true", help="run a real restart using the local config after safety checks")
    args = parser.parse_args(argv)

    do_detect = args.detect or args.write or args.dry_run or not args.test
    config: dict[str, Any] | None = None
    if do_detect:
        config, evidence = detect_config()
        normalized, errors = validate_local_restart_config(config)
        if errors:
            print(json.dumps({"ok": False, "errors": errors, "detected": config}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps({"ok": True, "detected": normalized, "listener_pid": evidence["listener"]["pid"]}, ensure_ascii=False, indent=2))
        if args.write:
            write_local_files(normalized)
            print(f"Wrote {LOCAL_RESTART_CONFIG_PATH}")
            print(f"Wrote {LOCAL_RESTART_ENV_PATH}")
    if args.test:
        if config is None:
            config = json.loads(LOCAL_RESTART_CONFIG_PATH.read_text(encoding="utf-8"))
        normalized, errors = validate_local_restart_config(config)
        if errors:
            print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
            return 2
        run_wrapper_test(LOCAL_RESTART_CONFIG_PATH, str(normalized["host"]), int(normalized["port"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
