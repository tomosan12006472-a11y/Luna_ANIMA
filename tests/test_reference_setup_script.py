from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import comfyui_reference_setup_plan as setup_plan


class ReferenceSetupScriptTests(unittest.TestCase):
    def test_manifest_download_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "comfy"
            outside = Path(temp_dir) / "outside.safetensors"
            manifest = [{"target_subdir": "../", "filename": outside.name, "url": "https://example.invalid/file"}]

            results = setup_plan.download_manifest_items(root, manifest, allow_download=True)

            self.assertIn("relative paths", results[0]["error"])
            self.assertFalse(outside.exists())

    def test_manifest_download_rejects_absolute_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "comfy"
            absolute = Path(temp_dir) / "absolute.safetensors"
            manifest = [{"target_subdir": "models/controlnet", "filename": str(absolute), "url": "https://example.invalid/file"}]

            results = setup_plan.download_manifest_items(root, manifest, allow_download=True)

            self.assertIn("relative paths", results[0]["error"])
            self.assertFalse(absolute.exists())

    def test_manifest_download_rejects_unapproved_target_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "comfy"
            manifest = [{"target_subdir": "user_data", "filename": "bad.safetensors", "url": "https://example.invalid/file"}]

            results = setup_plan.download_manifest_items(root, manifest, allow_download=True)

            self.assertIn("target_subdir must be one of", results[0]["error"])
            self.assertFalse((root / "user_data" / "bad.safetensors").exists())

    def test_manifest_download_uses_tmp_then_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "comfy"
            manifest = [{"target_subdir": "models/controlnet", "filename": "ok.safetensors", "url": "https://example.invalid/file"}]

            def fake_download(url: str, target: Path) -> None:
                target.write_bytes(b"ok")

            with mock.patch.object(setup_plan, "urlretrieve", side_effect=fake_download):
                results = setup_plan.download_manifest_items(root, manifest, allow_download=True)

            target = root / "models" / "controlnet" / "ok.safetensors"
            self.assertTrue(results[0]["downloaded"])
            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes(), b"ok")
            self.assertFalse((target.parent / "ok.safetensors.tmp").exists())


if __name__ == "__main__":
    unittest.main()
