from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest
from unittest import mock

from app import payload_builder
import app.workflow.base as workflow_base
import app.workflow.detailer as workflow_detailer
import app.workflow.hires as workflow_hires
import app.workflow.loras as workflow_loras
import app.workflow.prompts as workflow_prompts


def stable_output_prefix(*, panel_id: str, generation_method: str, original_prefix: str, now=None) -> str:
    return f"20990101/{panel_id}/{generation_method}/{original_prefix}"


def base_request() -> dict[str, object]:
    return {
        "workflow_mode": "anima",
        "model": "Anima\\anima-preview3-base.safetensors",
        "text_encoder": "qwen_3_06b_base.safetensors",
        "vae": "qwen_image_vae.safetensors",
        "sampler": "er_sde",
        "scheduler": "simple",
        "steps": 28,
        "cfg": 4.25,
        "denoise": 1.0,
        "width": 896,
        "height": 1280,
        "seed": 123456789,
        "shift": 4.25,
        "rating": "safe",
        "quality_preset": "standard",
        "meta_prompt": "anime illustration",
        "year_prompt": "newest",
        "character1": "None",
        "character2": "None",
        "character3": "None",
        "original_character": "None",
        "common_prompt": "clean lineart",
        "outfit_prompt": "silver armor",
        "expression_prompt": "smile",
        "pose_prompt": "standing",
        "background_prompt": "simple background",
        "camera_prompt": "medium shot",
        "lighting_prompt": "soft lighting",
        "natural_description": "A composed character portrait.",
        "positive_prompt": "sharp eyes",
        "negative_preset": "light",
        "negative_prompt": "text, logo",
        "negative_prompt_raw": "text, logo",
        "negative_prompt_mode": "append",
        "prompt_ban": "",
        "loras": [],
        "official_loras": {"highres": {"enabled": False}, "turbo": {"enabled": False, "version": "v0.2"}},
        "dynamic_prompt": {"enabled": False},
        "hires_fix": {"enabled": False},
        "reference_assist": {"enabled": False, "apply_to_payload": False},
        "reference_modules": {"enabled": True, "outfit": {"enabled": False}, "pose": {"enabled": False}},
        "image_to_image": {"enabled": False, "apply_to_payload": False},
        "face_detailer": {"enabled": False},
        "hand_detailer": {"enabled": False},
    }


def summarize_payload(payload: dict[str, object]) -> dict[str, object]:
    workflow = payload["prompt"]
    assert isinstance(workflow, dict)
    ordered = sorted(workflow.keys())
    sampler_inputs = workflow.get("19", {}).get("inputs", {}) if isinstance(workflow.get("19"), dict) else {}
    return {
        "node_ids": ordered,
        "classes": {key: workflow[key].get("class_type") for key in ordered},
        "input_keys": {key: sorted((workflow[key].get("inputs") or {}).keys()) for key in ordered},
        "save_images": workflow.get("1", {}).get("inputs", {}).get("images"),
        "ksampler": {key: sampler_inputs.get(key) for key in ("model", "positive", "negative", "latent_image")},
    }


class WorkflowModuleTests(unittest.TestCase):
    def output_prefix_patches(self):
        return (
            mock.patch.object(payload_builder, "build_output_prefix", stable_output_prefix),
            mock.patch.object(workflow_base, "build_output_prefix", stable_output_prefix),
            mock.patch.object(workflow_detailer, "build_output_prefix", stable_output_prefix),
        )

    def test_helper_outputs_match_payload_builder_facade(self) -> None:
        request = base_request()
        self.assertEqual(payload_builder.build_prompts(deepcopy(request)), workflow_prompts.build_prompts(deepcopy(request)))

        hires_request = deepcopy(request)
        hires_request["hires_fix"] = {
            "enabled": True,
            "upscale_factor": 1.3,
            "target_width": 1408,
            "target_height": 1792,
        }
        self.assertEqual(payload_builder.compute_hires_size(deepcopy(hires_request)), workflow_hires.compute_hires_size(deepcopy(hires_request)))

        paths = {
            payload_builder.ANIMA_HIGHRES_LORA_NAME: "D:/golden/lora/highres.safetensors",
            payload_builder.ANIMA_TURBO_LORA_V01_NAME: "D:/golden/lora/turbo_v01.safetensors",
            payload_builder.ANIMA_TURBO_LORA_V02_NAME: "D:/golden/lora/turbo_v02.safetensors",
        }
        fake_find = lambda name: paths.get(name, "")
        lora_request = {
            "official_loras": {
                "highres": {"enabled": True, "strength": 0.55},
                "turbo": {"enabled": True, "version": "auto", "strength": 0.45, "preset_applied": True},
            }
        }
        with mock.patch.object(payload_builder, "find_lora_file", fake_find), mock.patch.object(workflow_loras, "find_lora_file", fake_find):
            self.assertEqual(payload_builder.resolve_official_loras(deepcopy(lora_request)), workflow_loras.resolve_official_loras(deepcopy(lora_request)))
            self.assertEqual(payload_builder.official_lora_summary(deepcopy(lora_request)), workflow_loras.official_lora_summary(deepcopy(lora_request)))

    def test_catalog_loras_skip_disabled_and_off_application(self) -> None:
        request = {
            **base_request(),
            "loras": [
                {"enabled": False, "name": "style/disabled.safetensors", "application": "model_clip", "strength_model": 0.4, "strength_clip": 0.2},
                {"enabled": True, "name": "style/off.safetensors", "application": "off", "strength_model": 0.8, "strength_clip": 0.8},
                {"name": "style/legacy-enabled.safetensors", "application": "model_only", "strength_model": 0.6, "strength_clip": 0.6},
            ],
        }

        with self.output_prefix_patches()[0], self.output_prefix_patches()[1], self.output_prefix_patches()[2]:
            payload = payload_builder.build_prompt_payload(deepcopy(request), "module-client")

        workflow = payload["prompt"]
        lora_nodes = {
            node_id: node
            for node_id, node in workflow.items()
            if isinstance(node, dict) and node.get("class_type") in {"LoraLoader", "LoraLoaderModelOnly"}
        }
        self.assertEqual(list(lora_nodes), ["9051"])
        self.assertEqual(lora_nodes["9051"]["class_type"], "LoraLoaderModelOnly")
        self.assertEqual(lora_nodes["9051"]["inputs"]["lora_name"], "style\\legacy-enabled.safetensors")
        self.assertEqual(workflow["46"]["inputs"]["model"], ["9051", 0])

    def test_generation_workflow_snapshots_match_facade(self) -> None:
        image_ref = {"name": "module.png", "subfolder": "", "type": "input"}
        cases: dict[str, tuple[dict[str, object], list[str], object, dict[str, object]]] = {
            "basic": (base_request(), ["1", "11", "12", "15", "19", "28", "44", "45", "46", "8"], ["8", 0], {"model": ["46", 0], "positive": ["11", 0], "negative": ["12", 0], "latent_image": ["28", 0]}),
            "hires": (
                {**base_request(), "hires_fix": {"enabled": True, "mode": "latent", "upscale_factor": 1.5, "latent_upscale_method": "bicubic", "denoise": 0.45, "steps": 15}},
                ["1", "11", "12", "15", "19", "28", "44", "45", "46", "8", "9200", "9201", "9202"],
                ["9202", 0],
                {"model": ["46", 0], "positive": ["11", 0], "negative": ["12", 0], "latent_image": ["28", 0]},
            ),
            "i2i": (
                {**base_request(), "image_to_image": {"enabled": True, "apply_to_payload": True, "comfyui_image": image_ref, "denoise": 0.5}},
                ["1", "11", "12", "15", "19", "28", "44", "45", "46", "8", "9100", "9101"],
                ["8", 0],
                {"model": ["46", 0], "positive": ["11", 0], "negative": ["12", 0], "latent_image": ["9101", 0]},
            ),
            "reference_modules": (
                {**base_request(), "reference_modules": {"enabled": True, "outfit": {"enabled": True, "apply_to_payload": True, "comfyui_image": image_ref}, "pose": {"enabled": False}}},
                ["1", "11", "12", "15", "19", "28", "44", "45", "46", "8", "9300", "9301"],
                ["8", 0],
                {"model": ["9301", 0], "positive": ["11", 0], "negative": ["12", 0], "latent_image": ["28", 0]},
            ),
            "background_reference_noop": (
                {**base_request(), "reference_modules": {"enabled": True, "outfit": {"enabled": False}, "pose": {"enabled": False}, "background": {"enabled": True, "apply_to_payload": False, "image_id": "bg_1"}}},
                ["1", "11", "12", "15", "19", "28", "44", "45", "46", "8"],
                ["8", 0],
                {"model": ["46", 0], "positive": ["11", 0], "negative": ["12", 0], "latent_image": ["28", 0]},
            ),
            "background_reference": (
                {
                    **base_request(),
                    "reference_modules": {
                        "enabled": True,
                        "outfit": {"enabled": False},
                        "pose": {"enabled": False},
                        "background": {
                            "enabled": True,
                            "apply_to_payload": True,
                            "comfyui_image": image_ref,
                            "mode": "depth",
                            "strength": 0.45,
                            "start_at": 0.0,
                            "end_at": 0.75,
                            "controlnet_model": "anima-depth-controlnet.safetensors",
                            "preprocessor_node_class": "DepthAnythingV2Preprocessor",
                            "preprocessor_inputs": {"image": "__image__", "resolution": 1024},
                            "image_resize_node_class": "ImageScale",
                            "resize_mode": "crop",
                        },
                    },
                },
                ["1", "11", "12", "15", "19", "28", "44", "45", "46", "8", "9500", "9501", "9502", "9503", "9504"],
                ["8", 0],
                {"model": ["46", 0], "positive": ["9504", 0], "negative": ["9504", 1], "latent_image": ["28", 0]},
            ),
            "face_detailer": (
                {**base_request(), "face_detailer": {"enabled": True, "steps": 10, "cfg": 4.5, "denoise": 0.28, "guide_size": 512, "max_size": 1024, "bbox_threshold": 0.45}},
                ["1", "11", "12", "15", "19", "28", "44", "45", "46", "8", "9300", "9301"],
                ["9301", 0],
                {"model": ["46", 0], "positive": ["11", 0], "negative": ["12", 0], "latent_image": ["28", 0]},
            ),
            "hand_detailer": (
                {**base_request(), "hand_detailer": {"enabled": True, "steps": 8, "cfg": 4.0, "denoise": 0.42, "bbox_threshold": 0.36, "lllite_strength": 0.9}},
                ["1", "11", "12", "15", "19", "28", "44", "45", "46", "8", "9300", "9301", "9400", "9401", "9402", "9403"],
                ["9301", 0],
                {"model": ["46", 0], "positive": ["11", 0], "negative": ["12", 0], "latent_image": ["28", 0]},
            ),
        }

        with self.output_prefix_patches()[0], self.output_prefix_patches()[1], self.output_prefix_patches()[2]:
            for _name, (request, expected_nodes, save_images, ksampler) in cases.items():
                facade_payload = payload_builder.build_prompt_payload(deepcopy(request), "module-client")
                module_payload = workflow_base.build_prompt_payload(deepcopy(request), "module-client")
                facade_summary = summarize_payload(facade_payload)
                self.assertEqual(facade_summary, summarize_payload(module_payload))
                self.assertEqual(facade_summary["node_ids"], expected_nodes)
                self.assertEqual(facade_summary["save_images"], save_images)
                self.assertEqual(facade_summary["ksampler"], ksampler)
                if _name == "background_reference":
                    workflow = facade_payload["prompt"]
                    self.assertEqual(workflow["9501"]["class_type"], "ImageScale")
                    self.assertEqual(workflow["9501"]["inputs"]["image"], ["9500", 0])
                    self.assertEqual(workflow["9501"]["inputs"]["width"], 896)
                    self.assertEqual(workflow["9501"]["inputs"]["height"], 1280)
                    self.assertEqual(workflow["9501"]["inputs"]["crop"], "center")
                    self.assertEqual(workflow["9502"]["inputs"]["image"], ["9501", 0])

    def test_detailer_postprocess_payloads_match_facade(self) -> None:
        face_request = {
            "model": "Anima\\anima-preview3-base.safetensors",
            "text_encoder": "qwen_3_06b_base.safetensors",
            "vae": "qwen_image_vae.safetensors",
            "shift": 4.0,
            "seed": 987654321,
            "positive_prompt": "anime illustration, detailed face",
            "negative_prompt": "bad anatomy, watermark",
            "official_loras": {"highres": {"enabled": False}, "turbo": {"enabled": False}},
            "loras": [],
            "face_detailer": {"enabled": True, "steps": 10, "cfg": 4.5, "denoise": 0.28, "guide_size": 512, "max_size": 1024, "bbox_threshold": 0.45},
        }
        hand_request = {
            "operation": "hand_detailer_postprocess",
            "model": "Anima\\anima-preview3-base.safetensors",
            "text_encoder": "qwen_3_06b_base.safetensors",
            "vae": "qwen_image_vae.safetensors",
            "shift": 4.0,
            "seed": 987654321,
            "positive_prompt": "anime illustration, detailed hands",
            "negative_prompt": "bad anatomy, watermark",
            "official_loras": {"highres": {"enabled": False}, "turbo": {"enabled": False}},
            "loras": [],
            "hand_detailer": {"enabled": True, "steps": 9, "cfg": 4.0, "denoise": 0.44, "bbox_threshold": 0.34, "lllite_strength": 0.88},
        }
        with self.output_prefix_patches()[0], self.output_prefix_patches()[1], self.output_prefix_patches()[2]:
            face_facade = payload_builder.build_face_detailer_postprocess_payload(deepcopy(face_request), "module-client", "module/source.png")
            face_module = workflow_detailer.build_face_detailer_postprocess_payload(deepcopy(face_request), "module-client", "module/source.png")
            hand_facade = payload_builder.build_hand_detailer_postprocess_payload(deepcopy(hand_request), "module-client", "module/source.png")
            hand_module = workflow_detailer.build_hand_detailer_postprocess_payload(deepcopy(hand_request), "module-client", "module/source.png")

        self.assertEqual(summarize_payload(face_facade), summarize_payload(face_module))
        self.assertEqual(summarize_payload(hand_facade), summarize_payload(hand_module))
        self.assertEqual(face_facade["prompt"]["1"]["inputs"]["images"], ["9301", 0])
        self.assertEqual(hand_facade["prompt"]["1"]["inputs"]["images"], ["9301", 0])

    def test_workflow_modules_do_not_import_payload_builder(self) -> None:
        workflow_dir = Path(__file__).resolve().parents[1] / "app" / "workflow"
        for path in workflow_dir.glob("*.py"):
            self.assertNotIn("payload_builder", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
