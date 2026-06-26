from __future__ import annotations

import importlib.util
from pathlib import Path, PureWindowsPath
import unittest


ROOT_DIR = Path(__file__).resolve().parents[1]


def load_configure_module():
    path = ROOT_DIR / "scripts" / "configure_comfyui_restart.py"
    spec = importlib.util.spec_from_file_location("configure_comfyui_restart", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ComfyUiRestartScriptTests(unittest.TestCase):
    def test_windows_command_line_parser_finds_main_script_and_args(self) -> None:
        module = load_configure_module()
        command = (
            r'"D:\AI\ComfyUI\venv\Scripts\python.exe" '
            r"D:\AI\ComfyUI\ComfyUI\main.py --output-directory D:\AI\ComfyUI\outputs --port 8188"
        )
        parts = module.split_windows_command_line(command)
        main = module.find_main_script([], parts)
        self.assertEqual(str(main), r"D:\AI\ComfyUI\ComfyUI\main.py")
        args = module.derive_args([], parts, main)
        self.assertEqual(args[0], r"D:\AI\ComfyUI\ComfyUI\main.py")
        self.assertIn("--port", args)

    def test_comfy_root_is_parent_of_comfyui_package_dir(self) -> None:
        module = load_configure_module()
        root = module.comfy_root_for_main(PureWindowsPath(r"D:\AI\ComfyUI\ComfyUI\main.py"))
        self.assertEqual(str(root), r"D:\AI\ComfyUI")

    def test_run_luna_anima_loads_machine_local_restart_env(self) -> None:
        script = (ROOT_DIR / "run_luna_anima.bat").read_text(encoding="utf-8")
        self.assertIn('if exist "user_data\\comfyui_restart_env.bat"', script)
        self.assertIn('call "user_data\\comfyui_restart_env.bat"', script)
        self.assertNotIn("D:\\AI\\ComfyUI", script)

    def test_run_luna_anima_verifies_listener_before_stopping(self) -> None:
        script = (ROOT_DIR / "run_luna_anima.bat").read_text(encoding="utf-8")
        self.assertIn("function Test-LunaProcess", script)
        self.assertIn("app\\.main:app", script)
        self.assertIn("uvicorn", script)
        self.assertIn("skip non-matching listener PID", script)
        self.assertIn("Get-CimInstance Win32_Process -Filter", script)

    def test_wrapper_does_not_target_all_python_processes(self) -> None:
        script = (ROOT_DIR / "scripts" / "restart_comfyui_windows.ps1").read_text(encoding="utf-8")
        self.assertNotIn("/IM python.exe", script)
        self.assertIn("Is-VerifiedComfyProcess", script)
        self.assertIn("taskkill.exe /PID", script)


if __name__ == "__main__":
    unittest.main()
