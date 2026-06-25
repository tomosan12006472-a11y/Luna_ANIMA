from __future__ import annotations

import os
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from app import comfyui_control
from app.comfyui_restart_config import local_restart_env_lines, validate_local_restart_config


def python_command(source: str) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([sys.executable, "-c", source])
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(source)}"


class ComfyUiControlTests(unittest.TestCase):
    def tearDown(self) -> None:
        comfyui_control._reset_restart_jobs_for_tests()

    def env(self, **values: str):
        keys = {
            "LUNA_COMFY_RESTART_ENABLED",
            "COMFYUI_RESTART_COMMAND",
            "COMFYUI_RESTART_TIMEOUT_SECONDS",
            "COMFYUI_RESTART_POLL_INTERVAL_SECONDS",
            "COMFYUI_RESTART_CWD",
            "COMFYUI_RESTART_SHELL",
            "COMFYUI_RESTART_CONFIG_PATH",
        }
        patch = {key: "" for key in keys}
        patch["COMFYUI_RESTART_CONFIG_PATH"] = str(Path(tempfile.gettempdir()) / "missing-comfyui-restart.local.json")
        patch.update(values)
        return mock.patch.dict(os.environ, patch, clear=False)

    def wait_for_status(self, *statuses: str, timeout: float = 3.0) -> dict:
        deadline = time.time() + timeout
        latest = {}
        while time.time() < deadline:
            latest = comfyui_control.latest_restart_status()
            status = latest.get("job", {}).get("status")
            if status in statuses:
                return latest
            time.sleep(0.05)
        return latest

    def test_restart_capability_disabled_by_default(self) -> None:
        with self.env(LUNA_COMFY_RESTART_ENABLED="0", COMFYUI_RESTART_COMMAND=""):
            capability = comfyui_control.restart_capability()
            result = comfyui_control.start_restart()

        self.assertTrue(capability["ok"])
        self.assertFalse(capability["enabled"])
        self.assertFalse(capability["configured"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "disabled")

    def test_restart_enabled_fake_command_reaches_ready(self) -> None:
        with (
            self.env(
                LUNA_COMFY_RESTART_ENABLED="1",
                COMFYUI_RESTART_COMMAND=python_command("print('restart ok')"),
                COMFYUI_RESTART_TIMEOUT_SECONDS="3",
                COMFYUI_RESTART_POLL_INTERVAL_SECONDS="0.05",
            ),
            mock.patch.object(comfyui_control, "load_settings", return_value={"api_addr": "127.0.0.1:8188"}),
            mock.patch.object(comfyui_control.comfy_client, "queue_info", return_value={"queue_running": [], "queue_pending": []}),
            mock.patch.object(comfyui_control.comfy_client, "object_info", return_value={"LoadImage": {}}),
        ):
            result = comfyui_control.start_restart()
            status = self.wait_for_status("ready")

        self.assertTrue(result["ok"])
        self.assertTrue(result["queued"])
        job = status["job"]
        self.assertEqual(job["status"], "ready")
        self.assertEqual(job["exit_code"], 0)
        self.assertTrue(job["comfy_reachable"])

    def test_restart_output_is_not_exposed_in_public_status(self) -> None:
        secret = "SECRET_SENTINEL_RESTART_OUTPUT"
        with (
            self.env(
                LUNA_COMFY_RESTART_ENABLED="1",
                COMFYUI_RESTART_COMMAND=python_command(f"print({secret!r})"),
                COMFYUI_RESTART_TIMEOUT_SECONDS="3",
                COMFYUI_RESTART_POLL_INTERVAL_SECONDS="0.05",
            ),
            mock.patch.object(comfyui_control, "load_settings", return_value={"api_addr": "127.0.0.1:8188"}),
            mock.patch.object(comfyui_control.comfy_client, "queue_info", return_value={"queue_running": [], "queue_pending": []}),
            mock.patch.object(comfyui_control.comfy_client, "object_info", return_value={"LoadImage": {}}),
        ):
            result = comfyui_control.start_restart()
            status = self.wait_for_status("ready")
            capability = comfyui_control.restart_capability()

        public_json = json.dumps({"result": result, "status": status, "capability": capability})
        self.assertNotIn(secret, public_json)
        self.assertNotIn("stdout_tail", public_json)
        self.assertNotIn("stderr_tail", public_json)

    def test_running_restart_prevents_duplicate(self) -> None:
        with (
            self.env(
                LUNA_COMFY_RESTART_ENABLED="1",
                COMFYUI_RESTART_COMMAND=python_command("import time; time.sleep(0.4); print('ok')"),
                COMFYUI_RESTART_TIMEOUT_SECONDS="3",
                COMFYUI_RESTART_POLL_INTERVAL_SECONDS="0.05",
            ),
            mock.patch.object(comfyui_control, "load_settings", return_value={"api_addr": "127.0.0.1:8188"}),
            mock.patch.object(comfyui_control.comfy_client, "queue_info", return_value={"queue_running": [], "queue_pending": []}),
            mock.patch.object(comfyui_control.comfy_client, "object_info", return_value={"LoadImage": {}}),
        ):
            first = comfyui_control.start_restart()
            second = comfyui_control.start_restart()
            final = self.wait_for_status("ready", timeout=4.0)

        self.assertTrue(first["queued"])
        self.assertFalse(second["queued"])
        self.assertEqual(second["job_id"], first["job_id"])
        self.assertEqual(final["job"]["status"], "ready")

    def test_restart_command_timeout_fails_job(self) -> None:
        with self.env(
            LUNA_COMFY_RESTART_ENABLED="1",
            COMFYUI_RESTART_COMMAND=python_command("import time; time.sleep(2)"),
            COMFYUI_RESTART_TIMEOUT_SECONDS="1",
            COMFYUI_RESTART_POLL_INTERVAL_SECONDS="0.05",
        ), mock.patch.object(comfyui_control.comfy_client, "queue_info", return_value={"queue_running": [], "queue_pending": []}):
            result = comfyui_control.start_restart()
            status = self.wait_for_status("failed", timeout=3.0)

        self.assertTrue(result["queued"])
        self.assertEqual(status["job"]["status"], "failed")
        self.assertIn("timed out", status["job"]["message"])

    def test_restart_exception_message_does_not_echo_command_path(self) -> None:
        secret = r"D:\secret\restart-token.bat"
        with (
            self.env(
                LUNA_COMFY_RESTART_ENABLED="1",
                COMFYUI_RESTART_COMMAND=secret,
                COMFYUI_RESTART_TIMEOUT_SECONDS="3",
                COMFYUI_RESTART_POLL_INTERVAL_SECONDS="0.05",
            ),
            mock.patch.object(comfyui_control, "load_settings", return_value={"api_addr": "127.0.0.1:8188"}),
            mock.patch.object(comfyui_control.comfy_client, "queue_info", return_value={"queue_running": [], "queue_pending": []}),
            mock.patch.object(comfyui_control.subprocess, "run", side_effect=OSError(f"cannot run {secret}")),
        ):
            result = comfyui_control.start_restart()
            status = self.wait_for_status("failed")

        self.assertTrue(result["queued"])
        self.assertEqual(status["job"]["status"], "failed")
        self.assertEqual(status["job"]["message"], "restart command failed")
        self.assertNotIn("secret", status["job"]["message"].lower())

    def test_queue_busy_refuses_restart(self) -> None:
        with (
            self.env(
                LUNA_COMFY_RESTART_ENABLED="1",
                COMFYUI_RESTART_COMMAND=python_command("print('should not run')"),
            ),
            mock.patch.object(comfyui_control, "load_settings", return_value={"api_addr": "127.0.0.1:8188"}),
            mock.patch.object(comfyui_control.comfy_client, "queue_info", return_value={"queue_running": [{"prompt_id": "a"}], "queue_pending": []}),
            mock.patch.object(comfyui_control.subprocess, "run") as run,
        ):
            result = comfyui_control.start_restart()

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "busy")
        run.assert_not_called()

    def test_local_restart_config_enables_wrapper_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ComfyRoot"
            main = root / "ComfyUI" / "main.py"
            python = root / "venv" / "Scripts" / "python.exe"
            main.parent.mkdir(parents=True)
            python.parent.mkdir(parents=True)
            main.write_text("print('comfy')\n", encoding="utf-8")
            python.write_text("", encoding="utf-8")
            config = {
                "enabled": True,
                "mode": "windows_wrapper",
                "comfyui_root": str(root),
                "python_executable": str(python),
                "main_script": str(main),
                "cwd": str(root),
                "args": [str(main), "--port", "8188"],
                "port": 8188,
            }
            config_path = Path(tmp) / "comfyui_restart.local.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.env(COMFYUI_RESTART_CONFIG_PATH=str(config_path), COMFYUI_RESTART_COMMAND=""):
                capability = comfyui_control.restart_capability()

        self.assertTrue(capability["configured"])
        self.assertTrue(capability["enabled"])
        self.assertEqual(capability["command_label"], "configured")

    def test_local_restart_config_missing_executable_is_disabled(self) -> None:
        config = {
            "enabled": True,
            "mode": "windows_wrapper",
            "comfyui_root": r"D:\missing\ComfyUI",
            "python_executable": r"D:\missing\python.exe",
            "main_script": r"D:\missing\ComfyUI\main.py",
            "cwd": r"D:\missing",
            "args": [r"D:\missing\ComfyUI\main.py"],
            "port": 8188,
        }
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "comfyui_restart.local.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.env(COMFYUI_RESTART_CONFIG_PATH=str(config_path), COMFYUI_RESTART_COMMAND=""):
                capability = comfyui_control.restart_capability()

        self.assertTrue(capability["configured"])
        self.assertFalse(capability["enabled"])
        self.assertEqual(capability["message"], "local restart config invalid")

    def test_wrapper_output_parser_exposes_safe_status_fields(self) -> None:
        parsed = comfyui_control._parse_restart_output("\ufeffold_pid=123\nnew_pid=456\nlog_available=true\nstage=starting\nsecret=value\n")
        self.assertEqual(parsed["old_pid"], 123)
        self.assertEqual(parsed["new_pid"], 456)
        self.assertTrue(parsed["log_available"])
        self.assertEqual(parsed["stage"], "starting")
        self.assertNotIn("secret", parsed)

    def test_wrapper_command_gets_status_file_argument(self) -> None:
        args = ["powershell.exe", "-File", r"D:\repo\scripts\restart_comfyui_windows.ps1", "-Config", "local.json"]
        updated = comfyui_control._args_with_status_file(args, Path(r"D:\tmp\status.txt"))
        self.assertEqual(updated[-2:], ["-StatusFile", r"D:\tmp\status.txt"])
        self.assertTrue(comfyui_control._is_windows_restart_wrapper(updated))

    def test_wrapper_new_pid_times_out_when_comfy_never_returns(self) -> None:
        job_id = "comfy-restart-timeout"
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(comfyui_control, "USER_DATA_DIR", Path(tmp)),
            mock.patch.object(comfyui_control, "load_settings", return_value={"api_addr": "127.0.0.1:8188"}),
            mock.patch.object(comfyui_control.comfy_client, "object_info", return_value={}),
        ):
            status_path = comfyui_control._job_status_path(job_id)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("old_pid=111\nnew_pid=222\nlog_available=true\n", encoding="utf-8")
            with comfyui_control._LOCK:
                comfyui_control._JOBS[job_id] = {
                    "job_id": job_id,
                    "status": "waiting_for_comfy",
                    "stage": "waiting_for_comfy",
                    "started_at": "2026-06-26T00:00:00",
                    "finished_at": None,
                    "started_monotonic": time.monotonic() - 2,
                    "timeout_seconds": 1,
                    "exit_code": None,
                    "comfy_reachable": False,
                    "message": "waiting for ComfyUI",
                    "command_label": "configured",
                }
                comfyui_control._LAST_JOB_ID = job_id
            status = comfyui_control.latest_restart_status()

        job = status["job"]
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["stage"], "failed")
        self.assertEqual(job["new_pid"], 222)
        self.assertIn("timed out", job["message"])

    def test_local_restart_config_validation_rejects_root_mismatch(self) -> None:
        normalized, errors = validate_local_restart_config(
            {
                "enabled": True,
                "mode": "windows_wrapper",
                "comfyui_root": r"D:\Comfy",
                "python_executable": r"D:\Comfy\venv\Scripts\python.exe",
                "main_script": r"D:\Other\ComfyUI\main.py",
                "cwd": r"D:\Comfy",
                "args": [r"D:\Other\ComfyUI\main.py"],
                "port": 8188,
            },
            require_exists=False,
        )
        self.assertEqual(normalized["port"], 8188)
        self.assertIn("main_script must be under comfyui_root", errors)

    def test_local_restart_env_uses_wrapper_without_shell(self) -> None:
        lines = "\n".join(local_restart_env_lines(Path(r"D:\repo\user_data\comfyui_restart.local.json")))
        self.assertIn("COMFYUI_RESTART_COMMAND=powershell.exe", lines)
        self.assertIn("restart_comfyui_windows.ps1", lines)
        self.assertIn('set "COMFYUI_RESTART_SHELL=0"', lines)


if __name__ == "__main__":
    unittest.main()
