from __future__ import annotations

import json
import unittest
from unittest import mock

from fastapi import HTTPException, Response

from app import main, reference_modules, validators


class MainRefactorBehaviorTests(unittest.TestCase):
    def test_validate_reference_modules_rejects_enabled_outfit_without_image(self) -> None:
        calls: list[str] = []

        def fake_availability(addr: str) -> dict:
            calls.append(addr)
            return {"reference_modules": {"outfit": {"available": True}, "pose": {"available": True}}}

        original_availability = validators.reference_modules_availability_payload
        validators.reference_modules_availability_payload = fake_availability
        try:
            response = validators.validate_reference_modules(
                main.GenerateRequest(reference_modules={"enabled": True, "outfit": {"enabled": True}, "pose": {"enabled": False}}),
                "127.0.0.1:8188",
            )
        finally:
            validators.reference_modules_availability_payload = original_availability
        self.assertTrue(calls, "availability stub was not used; patch target is wrong again")
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body.decode("utf-8"))
        self.assertEqual(body["stage"], "validate_reference_modules")
        self.assertEqual(body["comfy_node_errors"]["missing"], "reference_modules.outfit.image_id")

    def test_reference_modules_separates_anima_lllite_from_pose_controlnet(self) -> None:
        info = {
            "LoadImage": {},
            "ControlNetLoader": {
                "input": {
                    "required": {
                        "control_net_name": [
                            [
                                "anima-lllite-inpainting-v2.safetensors",
                                "anima-lllite-regional-exp-v3.safetensors",
                                "xinsir_controlnet_union_sdxl.safetensors",
                            ]
                        ]
                    }
                }
            },
            "ControlNetApplyAdvanced": {},
            "SetUnionControlNetType": {},
            "AnimaLLLiteApply": {
                "input": {
                    "required": {
                        "lllite_name": [
                            [
                                "anima-lllite-inpainting-v2.safetensors",
                                "anima-lllite-regional-exp-v3.safetensors",
                            ]
                        ]
                    },
                    "optional": {"mask": ["MASK"]},
                }
            },
        }

        modules = reference_modules.reference_module_capabilities(info, app_scope="anima")["reference_modules"]

        self.assertEqual(modules["pose"]["controlnet_models"], ["xinsir_controlnet_union_sdxl.safetensors"])
        self.assertTrue(modules["anima_lllite"]["available"])
        self.assertEqual(modules["anima_lllite"]["inpainting_model"], "anima-lllite-inpainting-v2.safetensors")
        self.assertEqual(modules["anima_lllite"]["regional_model"], "anima-lllite-regional-exp-v3.safetensors")
        self.assertTrue(modules["anima_lllite"]["mask_supported"])

    def test_diagnostics_requires_auth(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            main.diagnostics(None)
        self.assertEqual(cm.exception.status_code, 401)

    def test_full_diagnostics_requires_auth(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            main.diagnostics_full(None)
        self.assertEqual(cm.exception.status_code, 401)

    def test_comfy_cache_reset_is_opt_in(self) -> None:
        data = main.GenerateRequest(character1="Scathach")
        with (
            mock.patch.object(main.comfy_client, "queue_info") as queue_info,
            mock.patch.object(main.comfy_client, "reset_execution_cache") as reset_execution_cache,
        ):
            response = main.reset_comfy_cache_for_character_prompt("127.0.0.1:8188", data)
        self.assertIsNone(response)
        queue_info.assert_not_called()
        reset_execution_cache.assert_not_called()

    def test_comfy_cache_reset_requires_empty_queue(self) -> None:
        data = main.GenerateRequest(character1="Scathach", reset_comfy_cache=True)
        with (
            mock.patch.object(main.comfy_client, "queue_info", return_value={"queue_running": [["running"]], "queue_pending": []}),
            mock.patch.object(main.comfy_client, "reset_execution_cache") as reset_execution_cache,
        ):
            response = main.reset_comfy_cache_for_character_prompt("127.0.0.1:8188", data)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 409)
        reset_execution_cache.assert_not_called()

    def test_history_known_revision_returns_unchanged_short_circuit(self) -> None:
        main.SESSIONS.add("test-session")
        try:
            with (
                mock.patch.object(main, "load_settings", return_value={"api_addr": "127.0.0.1:8188"}),
                mock.patch.object(main, "refresh_pending_history_items", return_value=False),
                mock.patch.object(main, "history_collection_revision", return_value="history-sig"),
                mock.patch.object(
                    main,
                    "history_page_with_flags",
                    return_value=([{"id": "hist-1", "created_at": "2026-06-11T10:00:00"}], [], {"total": 1}, 1),
                ),
            ):
                first = main.history(Response(), limit=20, offset=0, view="list", anima_claude_session="test-session")
                second = main.history(
                    Response(),
                    limit=20,
                    offset=0,
                    view="list",
                    known_revision=str(first["revision"]),
                    anima_claude_session="test-session",
                )
        finally:
            main.SESSIONS.discard("test-session")
        self.assertFalse(first["unchanged"])
        self.assertTrue(second["unchanged"])
        self.assertEqual(second["revision"], first["revision"])
        self.assertNotIn("items", second)


if __name__ == "__main__":
    unittest.main()
