from __future__ import annotations

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import payload_builder
from app.api import generation as generation_api
from app.config import APP_PIN
from app.generation_prepare import generation_request_dict
from app.main import app
from app.schemas.generation import GenerateRequest, HiresFixSettings, OfficialLorasSettings
from app.schemas.reference import ImageToImageSettings, ReferenceAssistSettings


class GenerationSchemaTests(unittest.TestCase):
    def test_generate_request_accepts_minimal_payload(self) -> None:
        data = GenerateRequest()

        self.assertEqual(data.workflow_mode, "anima")
        self.assertFalse(data.hires_fix.enabled)
        self.assertFalse(data.image_to_image.enabled)
        self.assertTrue(data.reference_modules.enabled)

    def test_generate_request_accepts_existing_ui_nested_dict_payload(self) -> None:
        data = GenerateRequest(
            hires_fix={"enabled": True, "mode": "latent", "upscale_factor": "1.5", "latent_upscale_method": "bicubic"},
            official_loras={"highres": {"enabled": True, "strength": "0.55"}, "turbo": {"enabled": True, "version": "v0.2"}},
            reference_assist={"enabled": True, "image_id": "ref_1", "strength": "0.4", "start_percent": "0.1", "end_percent": "0.8"},
            reference_modules={"enabled": True, "outfit": {"enabled": True, "image_id": "outfit_1"}, "pose": {"enabled": False}},
            image_to_image={"enabled": True, "image_id": "i2i_1", "denoise": "0.42", "resize_mode": "cover", "allow_with_hires_fix": True},
            dynamic_prompt={"enabled": True, "wildcard_seed": "123"},
            prompt_random_collect={"enabled": True, "mode": "positive_completion", "include_characters": "false"},
            face_detailer={"enabled": True, "steps": "8", "denoise": "0.25"},
            hand_detailer={"enabled": True, "lllite_strength": "0.9"},
        )

        dumped = data.model_dump()
        self.assertTrue(dumped["hires_fix"]["enabled"])
        self.assertEqual(dumped["reference_modules"]["outfit"]["image_id"], "outfit_1")
        self.assertEqual(dumped["image_to_image"]["resize_mode"], "cover")
        self.assertFalse(dumped["prompt_random_collect"]["include_characters"])

    def test_hires_fix_defaults_clamp_and_mode_fallback(self) -> None:
        data = HiresFixSettings.model_validate({"enabled": True, "mode": "bad", "upscale_factor": 99, "denoise": -1, "steps": 999})

        self.assertEqual(data.mode, "latent")
        self.assertEqual(data.upscale_factor, 4.0)
        self.assertEqual(data.denoise, 0.0)
        self.assertEqual(data.steps, 60)

    def test_image_to_image_denoise_and_resize_mode_fallback(self) -> None:
        data = ImageToImageSettings.model_validate({"enabled": True, "denoise": 0, "resize_mode": "bad"})

        self.assertEqual(data.denoise, 0.01)
        self.assertEqual(data.resize_mode, "fit")

    def test_reference_assist_clamps_strength_and_percent(self) -> None:
        data = ReferenceAssistSettings.model_validate({"enabled": True, "strength": 9, "start_percent": -1, "end_percent": 2})

        self.assertEqual(data.strength, 1.0)
        self.assertEqual(data.start_percent, 0.0)
        self.assertEqual(data.end_percent, 1.0)

    def test_official_loras_turbo_version_fallback(self) -> None:
        data = OfficialLorasSettings.model_validate({"turbo": {"enabled": True, "version": "bad", "strength": 2}})

        self.assertEqual(data.turbo.version, "auto")
        self.assertEqual(data.turbo.strength, 1.0)

    def test_generation_request_dict_keeps_plain_dict_structure(self) -> None:
        data = GenerateRequest(
            character1="None",
            reference_modules={"enabled": True, "outfit": {"enabled": False}, "pose": {"enabled": False}},
            image_to_image={"enabled": False},
            dynamic_prompt={"enabled": False},
        )

        request_data = generation_request_dict(data)

        for key in (
            "hires_fix",
            "official_loras",
            "reference_assist",
            "reference_modules",
            "image_to_image",
            "dynamic_prompt",
            "prompt_random_collect",
            "face_detailer",
            "hand_detailer",
        ):
            self.assertIsInstance(request_data[key], dict)
        self.assertNotIn("wildcard_seed", request_data["dynamic_prompt"])
        self.assertEqual(request_data["reference_assist"]["app_scope"], "anima")
        self.assertEqual(request_data["image_to_image"]["resize_mode"], "fit")
        self.assertEqual(request_data["reference_modules"]["preset"], "off")

    def test_payload_preview_major_structure_is_stable(self) -> None:
        client = TestClient(app)
        client.post("/api/login", json={"pin": APP_PIN})

        request = {
            "character1": "None",
            "character2": "None",
            "character3": "None",
            "original_character": "None",
            "seed_mode": "fixed",
            "seed": 123456789,
            "reference_modules": {"enabled": False},
            "dynamic_prompt": {"enabled": False},
            "prompt_random_collect": {"enabled": False},
        }
        lora_paths = {
            payload_builder.ANIMA_HIGHRES_LORA_NAME: "D:/test/lora/highres.safetensors",
            payload_builder.ANIMA_TURBO_LORA_V01_NAME: "D:/test/lora/turbo_v01.safetensors",
            payload_builder.ANIMA_TURBO_LORA_V02_NAME: "D:/test/lora/turbo_v02.safetensors",
        }
        with (
            mock.patch.object(generation_api, "prepare_reference_request", side_effect=lambda request_data, addr, upload: request_data),
            mock.patch.object(generation_api, "prepare_reference_modules_request", side_effect=lambda request_data, addr, upload: request_data),
            mock.patch.object(generation_api, "prepare_i2i_request", side_effect=lambda request_data, addr, upload: request_data),
            mock.patch.object(payload_builder, "find_lora_file", side_effect=lambda name: lora_paths.get(name, "")),
        ):
            response = client.post("/api/payload/preview", json=request)

        body = response.json()
        payload = body["payload"]["prompt"]
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(sorted(payload.keys()), ["1", "11", "12", "15", "19", "28", "44", "45", "46", "8"])
        self.assertEqual(payload["19"]["class_type"], "KSampler")
        self.assertEqual(sorted(payload["19"]["inputs"].keys()), ["cfg", "denoise", "latent_image", "model", "negative", "positive", "sampler_name", "scheduler", "seed", "steps"])
        self.assertEqual(body["size"]["final_width"], 1024)
        self.assertEqual(body["official_loras"]["turbo"]["version"], "v0.2")


if __name__ == "__main__":
    unittest.main()
