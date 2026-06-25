from __future__ import annotations

import os
import json
import shlex
import subprocess
import sys
import time
import unittest
from unittest import mock

from app import comfyui_control


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
        }
        patch = {key: "" for key in keys}
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
        ):
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
            mock.patch.object(comfyui_control.subprocess, "run", side_effect=OSError(f"cannot run {secret}")),
        ):
            result = comfyui_control.start_restart()
            status = self.wait_for_status("failed")

        self.assertTrue(result["queued"])
        self.assertEqual(status["job"]["status"], "failed")
        self.assertEqual(status["job"]["message"], "restart command failed")
        self.assertNotIn("secret", status["job"]["message"].lower())


if __name__ == "__main__":
    unittest.main()
