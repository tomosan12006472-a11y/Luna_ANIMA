from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app import reference_modules


class ReferenceSetupDiagnosticsTests(unittest.TestCase):
    def test_reference_setup_detects_ipadapter_controlnet_and_aux(self) -> None:
        info = {
            "LoadImage": {},
            "easy ipadapterApply": {
                "input": {
                    "required": {
                        "preset": [[
                            "REGULAR - FLUX and SD3.5 only (high strength)",
                        ]],
                        "provider": [["CUDA"]],
                    }
                }
            },
            "CLIPVisionLoader": {"input": {"required": {"clip_name": [["clip-vit.safetensors"]]}}},
            "IPAdapterModelLoader": {"input": {"required": {"ipadapter_file": [["ipadapter-anima.safetensors"]]}}},
            "ControlNetLoader": {
                "input": {
                    "required": {
                        "control_net_name": [[
                            "anima-depth-controlnet.safetensors",
                            "anima-canny-controlnet.safetensors",
                            "xinsir_controlnet_union_sdxl.safetensors",
                        ]]
                    }
                }
            },
            "ControlNetApplyAdvanced": {},
            "SetUnionControlNetType": {},
            "ImageScale": {},
            "DepthAnythingV2Preprocessor": {"input": {"required": {"image": ["IMAGE"]}}},
            "CannyEdgePreprocessor": {"input": {"required": {"image": ["IMAGE"]}}},
            "AIO Aux Preprocessor": {},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "models" / "clip_vision").mkdir(parents=True)
            (root / "models" / "clip_vision" / "clip-vit.safetensors").write_bytes(b"")
            (root / "models" / "ipadapter").mkdir(parents=True)
            (root / "models" / "ipadapter" / "ipadapter-anima.safetensors").write_bytes(b"")
            (root / "models" / "controlnet").mkdir(parents=True)
            (root / "custom_nodes" / "comfyui_controlnet_aux" / "ckpts").mkdir(parents=True)

            setup = reference_modules.reference_setup_diagnostics(info, comfyui_roots=[root], app_scope="anima")

        self.assertEqual(setup["summary"]["outfit"], "available")
        self.assertIn("easy ipadapterApply", setup["outfit"]["ipadapter_nodes"])
        self.assertIn("easy ipadapterApply", setup["outfit"]["ipadapter_apply_nodes"])
        self.assertIn("clip-vit.safetensors", setup["outfit"]["clip_vision_models"]["found"])
        self.assertIn("ipadapter-anima.safetensors", setup["outfit"]["ipadapter_models"]["ipadapter_dir"]["found"])
        self.assertEqual(setup["summary"]["controlnet_aux"], "available")
        self.assertTrue(setup["background"]["modes"]["depth"]["available"])
        self.assertTrue(setup["background"]["modes"]["canny"]["available"])
        self.assertNotIn("ControlNetLoader", setup["missing_nodes"])

    def test_reference_setup_reports_missing_nodes_and_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            setup = reference_modules.reference_setup_diagnostics({}, comfyui_roots=[Path(temp_dir)], app_scope="anima")

        self.assertEqual(setup["summary"]["outfit"], "missing")
        self.assertIn("IPAdapter apply node", setup["outfit"]["missing_nodes"])
        self.assertIn("clip_vision model", setup["outfit"]["missing_models"])
        self.assertIn("ControlNetLoader", setup["missing_nodes"])
        self.assertTrue(any("model" in item for item in setup["missing_models"]))

    def test_reference_setup_accepts_non_easy_ipadapter_install(self) -> None:
        info = {
            "LoadImage": {},
            "IPAdapter Advanced": {},
            "CLIPVisionLoader": {"input": {"required": {"clip_name": [["clip-vit.safetensors"]]}}},
            "IPAdapterModelLoader": {"input": {"required": {"ipadapter_file": [["ipadapter-anima.safetensors"]]}}},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            setup = reference_modules.reference_setup_diagnostics(info, comfyui_roots=[Path(temp_dir)], app_scope="anima")

        self.assertEqual(setup["summary"]["outfit"], "available")
        self.assertTrue(setup["outfit"]["available"])
        self.assertFalse(setup["outfit"]["workflow_apply_available"])
        self.assertIn("IPAdapter Advanced", setup["outfit"]["ipadapter_nodes"])
        self.assertIn("IPAdapter Advanced", setup["outfit"]["ipadapter_apply_nodes"])
        self.assertNotIn("easy ipadapterApply", setup["outfit"]["missing_nodes"])
        self.assertTrue(any("workflow application currently uses easy ipadapterApply" in warning for warning in setup["outfit"]["warnings"]))

    def test_reference_setup_does_not_count_ipadapter_model_loader_as_apply_node(self) -> None:
        info = {
            "LoadImage": {},
            "CLIPVisionLoader": {"input": {"required": {"clip_name": [["clip-vit.safetensors"]]}}},
            "IPAdapterModelLoader": {"input": {"required": {"ipadapter_file": [["ipadapter-anima.safetensors"]]}}},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            setup = reference_modules.reference_setup_diagnostics(info, comfyui_roots=[Path(temp_dir)], app_scope="anima")

        self.assertEqual(setup["summary"]["outfit"], "missing")
        self.assertFalse(setup["outfit"]["available"])
        self.assertIn("IPAdapterModelLoader", setup["outfit"]["ipadapter_nodes"])
        self.assertEqual(setup["outfit"]["ipadapter_apply_nodes"], [])
        self.assertIn("IPAdapter apply node", setup["outfit"]["missing_nodes"])

    def test_reference_setup_reports_background_mapping_disabled(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(reference_modules, "_background_reference_mapping", return_value={"enabled": False, "modes": {}}),
        ):
            setup = reference_modules.reference_setup_diagnostics({"LoadImage": {}}, comfyui_roots=[Path(temp_dir)], app_scope="anima")

        self.assertEqual(setup["summary"]["background"], "missing")
        self.assertIn("background_reference mapping", setup["background"]["missing_nodes"])

    def test_reference_setup_reports_configured_background_model_missing_when_choices_empty(self) -> None:
        info = {
            "LoadImage": {},
            "ControlNetLoader": {"input": {"required": {"control_net_name": [[]]}}},
            "ControlNetApplyAdvanced": {},
            "ImageScale": {},
            "DepthAnythingV2Preprocessor": {"input": {"required": {"image": ["IMAGE"]}}},
        }
        mapping = {
            "enabled": True,
            "loader_node_class": "ControlNetLoader",
            "apply_node_class": "ControlNetApplyAdvanced",
            "image_resize_node_class": "ImageScale",
            "modes": {"depth": {"preprocessor_node_class": "DepthAnythingV2Preprocessor", "controlnet_model": "missing-depth.safetensors"}},
        }

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(reference_modules, "_background_reference_mapping", return_value=mapping),
        ):
            setup = reference_modules.reference_setup_diagnostics(info, comfyui_roots=[Path(temp_dir)], app_scope="anima")

        depth = setup["background"]["modes"]["depth"]
        self.assertFalse(depth["available"])
        self.assertIn("background_controlnet_model:missing-depth.safetensors", depth["missing_models"])
        self.assertEqual(setup["summary"]["background"], "missing")


if __name__ == "__main__":
    unittest.main()
