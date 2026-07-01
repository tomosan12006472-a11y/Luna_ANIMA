from __future__ import annotations

import json
import unittest
from unittest import mock
from pathlib import Path

from fastapi.testclient import TestClient

from app import diagnostics_helpers
from app import payload_builder
from app import validators
from app.api import generation as generation_api
from app.api import reference as reference_api
from app.config import APP_PIN
from app.generation_prepare import generation_request_dict
from app.main import app
from app.face_detailer import detailer_preset_settings, sanitize_face_detailer_settings, sanitize_hand_detailer_settings
from app.schemas.generation import FaceDetailerRequestSettings, GenerateRequest, HandDetailerRequestSettings, HiresFixSettings, OfficialLorasSettings
from app.schemas.reference import ImageToImageSettings, ReferenceAssistSettings
from app.workflow import loras as workflow_loras


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
            reference_modules={"enabled": True, "outfit": {"enabled": True, "image_id": "outfit_1"}, "pose": {"enabled": False}, "background": {"enabled": True, "image_id": "bg_1", "mode": "canny"}},
            image_to_image={"enabled": True, "image_id": "i2i_1", "denoise": "0.42", "resize_mode": "cover", "allow_with_hires_fix": True},
            dynamic_prompt={"enabled": True, "wildcard_seed": "123"},
            prompt_random_collect={"enabled": True, "mode": "positive_completion", "include_characters": "false"},
            face_detailer={"enabled": True, "steps": "8", "denoise": "0.25"},
            hand_detailer={"enabled": True, "lllite_strength": "0.9"},
        )

        dumped = data.model_dump()
        self.assertTrue(dumped["hires_fix"]["enabled"])
        self.assertEqual(dumped["reference_modules"]["outfit"]["image_id"], "outfit_1")
        self.assertEqual(dumped["reference_modules"]["background"]["mode"], "canny")
        self.assertEqual(dumped["image_to_image"]["resize_mode"], "cover")
        self.assertFalse(dumped["prompt_random_collect"]["include_characters"])

    def test_detailer_detection_controls_are_preserved_and_clamped(self) -> None:
        data = GenerateRequest(
            face_detailer={
                "enabled": True,
                "preset": "aggressive",
                "bbox_threshold": "2",
                "min_area_ratio": "0.02",
                "max_area_ratio": "0.01",
                "max_detections": "999",
                "runaway_guard_enabled": "false",
                "runaway_max_candidates": "999",
                "runaway_action": "limit",
            },
            hand_detailer={
                "enabled": True,
                "preset": "safe",
                "bbox_threshold": "0",
                "max_detections": "0",
                "runaway_guard_enabled": "true",
                "runaway_max_candidates": "0",
                "runaway_action": "bad",
            },
        )

        dumped = data.model_dump()
        face = dumped["face_detailer"]
        hand = dumped["hand_detailer"]
        self.assertEqual(face["preset"], "aggressive")
        self.assertEqual(face["bbox_threshold"], 0.95)
        self.assertEqual(face["max_area_ratio"], face["min_area_ratio"])
        self.assertEqual(face["max_detections"], 64)
        self.assertFalse(face["runaway_guard_enabled"])
        self.assertEqual(face["runaway_max_candidates"], 128)
        self.assertEqual(face["runaway_action"], "limit")
        self.assertEqual(hand["preset"], "safe")
        self.assertEqual(hand["bbox_threshold"], 0.05)
        self.assertEqual(hand["max_detections"], 1)
        self.assertTrue(hand["runaway_guard_enabled"])
        self.assertEqual(hand["runaway_max_candidates"], 1)
        self.assertEqual(hand["runaway_action"], "skip")

    def test_hand_detailer_default_bbox_matches_normal_preset(self) -> None:
        self.assertEqual(HandDetailerRequestSettings().bbox_threshold, 0.45)
        self.assertEqual(sanitize_hand_detailer_settings({})["bbox_threshold"], 0.45)

    def test_face_detailer_default_max_area_allows_large_crops(self) -> None:
        self.assertEqual(FaceDetailerRequestSettings().max_area_ratio, 1.0)
        self.assertEqual(sanitize_face_detailer_settings({})["max_area_ratio"], 1.0)
        for preset in ("safe", "normal", "aggressive"):
            self.assertEqual(detailer_preset_settings("face", preset)["max_area_ratio"], 1.0)

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

    def test_background_reference_defaults_and_clamps(self) -> None:
        data = GenerateRequest(
            reference_modules={
                "enabled": True,
                "outfit": {"enabled": True, "strength": 9},
                "pose": {"enabled": True, "strength": 9},
                "background": {
                    "enabled": True,
                    "image_id": "bg_1",
                    "mode": "unknown",
                    "strength": 9,
                    "start_at": 2,
                    "end_at": -1,
                    "resize_mode": "bad",
                },
            }
        )

        background = data.model_dump()["reference_modules"]["background"]
        self.assertEqual(data.reference_modules.outfit.strength, 1.0)
        self.assertEqual(data.reference_modules.pose.strength, 1.0)
        self.assertEqual(background["mode"], "depth")
        self.assertEqual(background["strength"], 1.5)
        self.assertEqual(background["start_at"], 1.0)
        self.assertEqual(background["end_at"], 1.0)
        self.assertEqual(background["resize_mode"], "crop")

    def test_official_loras_turbo_version_fallback(self) -> None:
        data = OfficialLorasSettings.model_validate({"turbo": {"enabled": True, "version": "bad", "strength": 4}})

        self.assertEqual(data.turbo.version, "auto")
        self.assertEqual(data.turbo.strength, 3.0)

    def test_official_loras_colorfix_defaults_and_clamps(self) -> None:
        default_data = OfficialLorasSettings.model_validate({"highres": {"enabled": True}})
        colorfix_data = OfficialLorasSettings.model_validate({"colorfix": {"enabled": "true", "strength": 2}})
        clamped_data = OfficialLorasSettings.model_validate({"colorfix": {"enabled": "true", "strength": 4}})

        self.assertFalse(default_data.colorfix.enabled)
        self.assertEqual(default_data.colorfix.strength, 0.6)
        self.assertTrue(colorfix_data.colorfix.enabled)
        self.assertEqual(colorfix_data.colorfix.strength, 2.0)
        self.assertEqual(clamped_data.colorfix.strength, 3.0)

    def test_generation_request_dict_keeps_plain_dict_structure(self) -> None:
        data = GenerateRequest(
            character1="None",
            loras=[
                {"enabled": False, "name": "style/off.safetensors", "application": "model_clip", "strength_model": "0.4", "strength_clip": "0.2"},
                {"name": "style/on.safetensors", "application": "model_only", "strength_model": "1.5"},
                {"enabled": True, "name": "style/legacy-off.safetensors", "application": "", "mode": "OFF"},
            ],
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
        self.assertIn("background", request_data["reference_modules"])
        self.assertFalse(request_data["reference_modules"]["background"]["enabled"])
        self.assertEqual(len(request_data["loras"]), 3)
        self.assertFalse(request_data["loras"][0]["enabled"])
        self.assertEqual(request_data["loras"][0]["application"], "model_clip")
        self.assertTrue(request_data["loras"][1]["enabled"])
        self.assertEqual(request_data["loras"][1]["application"], "model_only")
        self.assertEqual(request_data["loras"][1]["strength_model"], 1.5)
        self.assertFalse(request_data["loras"][2]["enabled"])
        self.assertEqual(request_data["loras"][2]["application"], "off")
        self.assertFalse(request_data["official_loras"]["colorfix"]["enabled"])
        self.assertEqual(request_data["official_loras"]["colorfix"]["strength"], 0.6)

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
            "loras": [
                {"enabled": False, "name": "style/off.safetensors", "application": "model_clip", "strength_model": 0.4, "strength_clip": 0.2}
            ],
            "official_lora_preset": "fast_preview",
            "reference_modules": {"enabled": False},
            "dynamic_prompt": {"enabled": False},
            "prompt_random_collect": {"enabled": False},
        }
        lora_paths = {
            payload_builder.ANIMA_HIGHRES_LORA_NAME: "D:/test/lora/highres.safetensors",
            payload_builder.ANIMA_TURBO_LORA_V01_NAME: "D:/test/lora/turbo_v01.safetensors",
            payload_builder.ANIMA_TURBO_LORA_V02_NAME: "D:/test/lora/turbo_v02.safetensors",
        }
        fake_find_lora = lambda name: lora_paths.get(name, "")
        with (
            mock.patch.object(generation_api, "prepare_reference_request", side_effect=lambda request_data, addr, upload: request_data),
            mock.patch.object(generation_api, "prepare_reference_modules_request", side_effect=lambda request_data, addr, upload: request_data),
            mock.patch.object(generation_api, "prepare_i2i_request", side_effect=lambda request_data, addr, upload: request_data),
            mock.patch.object(payload_builder, "find_lora_file", side_effect=fake_find_lora),
            mock.patch.object(workflow_loras, "find_lora_file", side_effect=fake_find_lora),
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
        self.assertEqual(body["official_lora_preset"], "fast_preview")
        self.assertIn("colorfix", body["official_loras"])
        self.assertFalse(body["official_loras"]["colorfix"]["enabled"])
        self.assertEqual(body["loras"][0]["name"], "style/off.safetensors")
        self.assertFalse(body["loras"][0]["enabled"])

    def test_generate_response_includes_comfy_cache_reset_metadata(self) -> None:
        client = TestClient(app)
        client.post("/api/login", json={"pin": APP_PIN})
        captured_request_data: dict[str, object] = {}

        def fake_create_pending_history_item(**kwargs):
            captured_request_data.update(kwargs["request_data"])
            return {"id": "hist-1"}

        request = {
            "character1": "Scathach",
            "character2": "None",
            "character3": "None",
            "original_character": "None",
            "reset_comfy_cache": True,
            "wait": False,
            "count": 1,
            "reference_modules": {"enabled": False},
            "dynamic_prompt": {"enabled": False},
            "prompt_random_collect": {"enabled": False},
        }
        with (
            mock.patch.object(generation_api.comfy_client, "queue_info", return_value={"queue_running": [], "queue_pending": []}),
            mock.patch.object(generation_api.comfy_client, "reset_execution_cache", return_value={"ok": True, "status": 200, "text": ""}),
            mock.patch.object(generation_api.comfy_client, "run_generation", return_value=generation_api.comfy_client.ComfyResult(ok=True, prompt_id="prompt-1", metrics={"submit_seconds": 0.01})),
            mock.patch.object(generation_api, "prepare_reference_request", side_effect=lambda request_data, addr, upload: request_data),
            mock.patch.object(generation_api, "prepare_reference_modules_request", side_effect=lambda request_data, addr, upload: request_data),
            mock.patch.object(generation_api, "prepare_i2i_request", side_effect=lambda request_data, addr, upload: request_data),
            mock.patch.object(generation_api, "build_prompt_payload_with_prompts", return_value=({"prompt": {}}, {"seed": 123, "positive": "p", "negative": "n", "characters": ["Scathach"]})),
            mock.patch.object(generation_api, "save_mobile_payload_data", return_value=Path("payload.json")),
            mock.patch.object(generation_api, "create_pending_history_item", side_effect=fake_create_pending_history_item),
            mock.patch.object(generation_api, "save_completed_generation_history"),
        ):
            response = client.post("/api/generate", json=request)

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["comfy_cache_reset"]["requested"])
        self.assertTrue(body["comfy_cache_reset"]["applied"])
        self.assertEqual(body["comfy_cache_reset"]["status"], 200)
        self.assertEqual(captured_request_data["comfy_cache_reset"]["applied"], True)
        self.assertEqual(body["items"][0]["comfy_cache_reset"]["applied"], True)

    def test_validate_official_loras_reports_missing_colorfix_when_enabled(self) -> None:
        data = GenerateRequest(official_loras={"colorfix": {"enabled": True, "strength": 0.55}})
        object_info = {
            "LoraLoaderModelOnly": {
                "input": {
                    "required": {
                        "lora_name": [["other.safetensors"]],
                    }
                }
            }
        }

        with (
            mock.patch.object(payload_builder, "find_lora_file", return_value=""),
            mock.patch.object(validators.comfy_client, "object_info", return_value=object_info),
        ):
            response = validators.validate_official_loras(data, "127.0.0.1:8188")

        self.assertIsNotNone(response)
        body = json.loads(response.body)
        self.assertIn(payload_builder.ANIMA_COLORFIX_LORA_NAME, body["comfy_node_errors"]["missing_files"])
        self.assertIn("missing_files", body["comfy_node_errors"])

    def test_official_lora_diagnostics_reports_colorfix_visibility(self) -> None:
        object_info = {
            "LoraLoaderModelOnly": {
                "input": {
                    "required": {
                        "lora_name": [[payload_builder.ANIMA_COLORFIX_LORA_NAME]],
                    }
                }
            }
        }
        fake_find_lora = lambda name: "D:/test/lora/colorfix.safetensors" if name == payload_builder.ANIMA_COLORFIX_LORA_NAME else ""

        with mock.patch.object(diagnostics_helpers, "find_lora_file", side_effect=fake_find_lora):
            diagnostics = diagnostics_helpers.official_lora_diagnostics(object_info)

        self.assertTrue(diagnostics["colorfix_lora_found"])
        self.assertEqual(diagnostics["colorfix_lora_file"], payload_builder.ANIMA_COLORFIX_LORA_NAME)
        self.assertTrue(diagnostics["colorfix_visible_to_comfy"])

    def test_reference_module_upload_accepts_background(self) -> None:
        client = TestClient(app)
        client.post("/api/login", json={"pin": APP_PIN})
        item = {
            "image_id": "bg_1",
            "filename": "background_reference.png",
            "path": str(Path(__file__)),
            "thumbnail_url": "/api/reference/images/bg_1/thumbnail",
            "image_url": "/api/reference/images/bg_1/image",
            "module": "background",
        }
        with (
            mock.patch.object(reference_api.reference_store, "save_reference_upload", return_value=item) as save_upload,
            mock.patch.object(reference_api.reference_store, "list_reference_images", return_value=[item]),
            mock.patch.object(reference_api.comfy_client, "upload_image", return_value={"ok": False, "status": 503, "text": "offline"}),
        ):
            response = client.post(
                "/api/reference-modules/upload?module=background",
                files={"file": ("bg.png", b"fake image", "image/png")},
            )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["item"]["module"], "background")
        save_upload.assert_called_once()


if __name__ == "__main__":
    unittest.main()
