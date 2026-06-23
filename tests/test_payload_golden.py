from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

from app import payload_builder


GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
UPDATE_GOLDEN = os.environ.get("UPDATE_GOLDEN") == "1"


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def assert_matches_golden(testcase: unittest.TestCase, name: str, value: object) -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_DIR / f"{name}.json"
    text = canonical_json(value)
    if UPDATE_GOLDEN:
        path.write_text(text, encoding="utf-8")
        return
    testcase.assertTrue(path.exists(), f"Missing golden file: {path}")
    testcase.assertEqual(path.read_text(encoding="utf-8"), text)


def stable_output_prefix(*, panel_id: str, generation_method: str, original_prefix: str, now=None) -> str:
    return f"20990101/{panel_id}/{generation_method}/{original_prefix}"


def base_request() -> dict[str, object]:
    return {
        "workflow_mode": "anima",
        "client_id": "golden-client",
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
        "pose_prompt": "__pose__",
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
        "loras": [
            {
                "enabled": True,
                "name": "style/example_lora.safetensors",
                "application": "model_clip",
                "strength_model": 0.7,
                "strength_clip": 0.25,
            }
        ],
        "official_loras": {
            "highres": {"enabled": False},
            "turbo": {"enabled": False, "version": "v0.2"},
        },
        "dynamic_prompt": {"enabled": True, "wildcard_seed": 24680},
        "hires_fix": {"enabled": False},
        "reference_assist": {"enabled": False, "apply_to_payload": False},
        "reference_modules": {"enabled": True, "outfit": {"enabled": False}, "pose": {"enabled": False}},
        "image_to_image": {"enabled": False, "apply_to_payload": False},
        "face_detailer": {"enabled": False},
        "hand_detailer": {"enabled": False},
    }


def catalog_loras_request() -> dict[str, object]:
    request = deepcopy(base_request())
    request.update(
        {
            "width": 1024,
            "height": 1536,
            "cfg": 4.5,
            "shift": None,
            "year_prompt": "",
            "common_prompt": "",
            "outfit_prompt": "white dress",
            "expression_prompt": "soft smile",
            "pose_prompt": "",
            "background_prompt": "library",
            "camera_prompt": "",
            "lighting_prompt": "",
            "natural_description": "",
            "positive_prompt": "ornate details",
            "negative_preset": "anima_recommended",
            "dynamic_prompt": {"enabled": False},
            "loras": [
                {
                    "enabled": True,
                    "name": "x/clip_pair.safetensors",
                    "application": "model_clip",
                    "strength_model": 0.8,
                    "strength_clip": 0.3,
                },
                {
                    "enabled": True,
                    "name": "y/model_only.safetensors",
                    "application": "model_only",
                    "strength_model": 0.65,
                },
                {
                    "enabled": True,
                    "name": "z/off.safetensors",
                    "application": "off",
                },
                {
                    "enabled": True,
                    "name": "w/legacy_mode.safetensors",
                    "mode": "Base",
                    "strength_model": 0.7,
                    "strength_clip": 0.7,
                },
                {
                    "enabled": True,
                    "name": "v/model_only_legacy.safetensors",
                    "application": "model_clip",
                    "model_strength": 0.65,
                },
            ],
        }
    )
    return request


class PayloadGoldenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_prefix = payload_builder.build_output_prefix
        payload_builder.build_output_prefix = stable_output_prefix

    def tearDown(self) -> None:
        payload_builder.build_output_prefix = self._original_prefix

    def test_resolve_official_loras(self) -> None:
        original_find = payload_builder.find_lora_file
        paths = {
            payload_builder.ANIMA_HIGHRES_LORA_NAME: "D:/golden/lora/highres.safetensors",
            payload_builder.ANIMA_TURBO_LORA_V01_NAME: "D:/golden/lora/turbo_v01.safetensors",
            payload_builder.ANIMA_TURBO_LORA_V02_NAME: "D:/golden/lora/turbo_v02.safetensors",
        }
        payload_builder.find_lora_file = lambda name: paths.get(name, "")
        try:
            request = {
                "official_loras": {
                    "highres": {"enabled": True, "strength": 0.55},
                    "turbo": {"enabled": True, "version": "auto", "strength": 0.45, "preset_applied": True},
                }
            }
            assert_matches_golden(self, "resolve_official_loras", payload_builder.resolve_official_loras(request))
        finally:
            payload_builder.find_lora_file = original_find

    def test_model_sampling_shift_metadata(self) -> None:
        assert_matches_golden(self, "model_sampling_shift_metadata", payload_builder.model_sampling_shift_metadata({"shift": "5.25"}))

    def test_build_prompts_dynamic_prompt(self) -> None:
        assert_matches_golden(self, "build_prompts_dynamic_prompt", payload_builder.build_prompts(deepcopy(base_request())))

    def test_stale_generated_natural_description_is_rebuilt(self) -> None:
        result = payload_builder.build_natural_description(
            ["埃列什基伽勒（Fate）"],
            {"natural_description": "An anime illustration of 摩根·勒·菲（Fate） in a clean, expressive composition."},
        )
        self.assertEqual(result, "An anime illustration of 埃列什基伽勒（Fate） in a clean, expressive composition.")

    def test_stale_generated_natural_description_is_dropped_without_characters(self) -> None:
        result = payload_builder.build_natural_description(
            [],
            {"natural_description": "An anime illustration of Jeanne D'arc from Fate in a clean, expressive composition."},
        )
        self.assertEqual(result, "")

    def test_manual_natural_description_is_preserved(self) -> None:
        result = payload_builder.build_natural_description(
            ["埃列什基伽勒（Fate）"],
            {"natural_description": "Morgan stands behind her in the background."},
        )
        self.assertEqual(result, "Morgan stands behind her in the background.")

    def test_manual_natural_description_is_preserved_without_characters(self) -> None:
        result = payload_builder.build_natural_description(
            [],
            {"natural_description": "A white-haired woman drinks at an izakaya."},
        )
        self.assertEqual(result, "A white-haired woman drinks at an izakaya.")

    def test_build_lora_sample_prompts(self) -> None:
        request = {
            **base_request(),
            "workflow_mode": payload_builder.LORA_SAMPLE_WORKFLOW_MODE,
            "model": payload_builder.LORA_SAMPLE_MODEL_NAME,
            "positive_prompt": "diagnostic pose, __pose__",
            "negative_prompt_mode": "custom",
        }
        assert_matches_golden(self, "build_lora_sample_prompts", payload_builder.build_lora_sample_prompts(deepcopy(request)))

    def test_original_identity_sentence_roles(self) -> None:
        entry = SimpleNamespace(
            display_name="Mira",
            identity_prompt="Mira is an original character with short black hair and blue eyes.",
        )
        result = {
            "left": payload_builder.original_identity_sentence(entry, "left"),
            "right": payload_builder.original_identity_sentence(entry, "right"),
            "support": payload_builder.original_identity_sentence(entry, "support"),
            "main": payload_builder.original_identity_sentence(entry, "main"),
        }
        assert_matches_golden(self, "original_identity_sentence_roles", result)

    def test_compute_hires_size_target_dimensions(self) -> None:
        request = {
            "width": 896,
            "height": 1280,
            "hires_fix": {
                "enabled": True,
                "upscale_factor": 1.3,
                "target_width": 1408,
                "target_height": 1792,
            },
        }
        assert_matches_golden(self, "compute_hires_size_target_dimensions", payload_builder.compute_hires_size(request))

    def test_build_prompt_payload_standard(self) -> None:
        payload = payload_builder.build_prompt_payload(deepcopy(base_request()), "golden-client")
        assert_matches_golden(self, "build_prompt_payload_standard", payload)

    def test_build_prompt_payload_catalog_loras(self) -> None:
        payload = payload_builder.build_prompt_payload(catalog_loras_request(), "golden-client")
        assert_matches_golden(self, "build_prompt_payload_catalog_loras", payload)

    def test_build_prompt_payload_hires_latent(self) -> None:
        request = deepcopy(base_request())
        request.update(
            {
                "workflow_mode": "anima_mobile_extended",
                "hires_fix": {
                    "enabled": True,
                    "mode": "latent",
                    "upscale_factor": 1.5,
                    "latent_upscale_method": "bicubic",
                    "denoise": 0.45,
                    "steps": 15,
                },
            }
        )
        payload = payload_builder.build_prompt_payload(request, "golden-client")
        assert_matches_golden(self, "build_prompt_payload_hires_latent", payload)

    def test_build_prompt_payload_hires_model(self) -> None:
        request = deepcopy(base_request())
        request.update(
            {
                "workflow_mode": "anima_mobile_extended",
                "hires_fix": {
                    "enabled": True,
                    "mode": "model",
                    "upscale_model": "RealESRGAN_x4.pth",
                    "target_width": 1344,
                    "target_height": 2016,
                },
            }
        )
        payload = payload_builder.build_prompt_payload(request, "golden-client")
        assert_matches_golden(self, "build_prompt_payload_hires_model", payload)

    def test_build_face_detailer_postprocess_payload(self) -> None:
        request = {
            "model": "Anima\\anima-preview3-base.safetensors",
            "text_encoder": "qwen_3_06b_base.safetensors",
            "vae": "qwen_image_vae.safetensors",
            "shift": 4.0,
            "seed": 987654321,
            "positive_prompt": "anime illustration, detailed face",
            "negative_prompt": "bad anatomy, watermark",
            "official_loras": {"highres": {"enabled": False}, "turbo": {"enabled": False}},
            "loras": [],
            "face_detailer": {
                "enabled": True,
                "steps": 10,
                "cfg": 4.5,
                "denoise": 0.28,
                "guide_size": 512,
                "max_size": 1024,
                "bbox_threshold": 0.45,
            },
        }
        payload = payload_builder.build_face_detailer_postprocess_payload(request, "golden-client", "golden/source.png")
        assert_matches_golden(self, "build_face_detailer_postprocess_payload", payload)

    def test_build_prompt_payload_hand_detailer_uses_lllite_mask(self) -> None:
        request = deepcopy(base_request())
        request["hand_detailer"] = {
            "enabled": True,
            "steps": 8,
            "cfg": 4.0,
            "denoise": 0.42,
            "bbox_threshold": 0.36,
            "lllite_strength": 0.9,
        }
        payload = payload_builder.build_prompt_payload(request, "golden-client")
        workflow = payload["prompt"]
        nodes = {node["class_type"]: node for node in workflow.values()}
        hand_nodes = [node for node in workflow.values() if node.get("_meta", {}).get("title") == "Hand Detailer"]
        lllite_node = nodes.get("AnimaLLLiteApply")
        segs_node = nodes.get("BboxDetectorSEGS")
        mask_node = nodes.get("SegsToCombinedMask")
        self.assertIsNotNone(lllite_node)
        self.assertIsNotNone(segs_node)
        self.assertIsNotNone(mask_node)
        self.assertEqual(lllite_node["inputs"]["lllite_name"], "anima-lllite-inpainting-v2.safetensors")
        self.assertEqual(lllite_node["inputs"]["mask"], [request["hand_detailer"]["lllite"]["mask_node_id"], 0])
        self.assertEqual(segs_node["inputs"]["labels"], "hand")
        self.assertEqual(hand_nodes[0]["inputs"]["bbox_detector"], [request["hand_detailer"]["detector_node_id"], 0])
        self.assertEqual(workflow["1"]["inputs"]["filename_prefix"], "20990101/anima/hand_detailer/Anima")
        self.assertTrue(request["hand_detailer"]["applied"])
        self.assertTrue(request["hand_detailer"]["lllite"]["applied"])

    def test_build_hand_detailer_postprocess_payload(self) -> None:
        request = {
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
            "hand_detailer": {
                "enabled": True,
                "steps": 9,
                "cfg": 4.0,
                "denoise": 0.44,
                "bbox_threshold": 0.34,
                "lllite_strength": 0.88,
            },
        }
        payload = payload_builder.build_hand_detailer_postprocess_payload(request, "golden-client", "golden/source.png")
        workflow = payload["prompt"]
        nodes = {node["class_type"]: node for node in workflow.values()}
        hand_nodes = [node for node in workflow.values() if node.get("_meta", {}).get("title") == "Hand Detailer"]
        self.assertEqual(workflow["1"]["inputs"]["filename_prefix"], "20990101/anima/hand_detailer_postprocess/AnimaHandDetailer")
        self.assertEqual(workflow["10"]["inputs"]["image"], "golden/source.png")
        self.assertEqual(nodes["AnimaLLLiteApply"]["inputs"]["image"], ["10", 0])
        self.assertEqual(nodes["AnimaLLLiteApply"]["inputs"]["mask"], [request["hand_detailer"]["lllite"]["mask_node_id"], 0])
        self.assertEqual(nodes["BboxDetectorSEGS"]["inputs"]["labels"], "hand")
        self.assertEqual(hand_nodes[0]["inputs"]["image"], ["10", 0])
        self.assertTrue(request["hand_detailer"]["applied"])
        self.assertTrue(request["hand_detailer"]["lllite"]["applied"])


if __name__ == "__main__":
    unittest.main()
