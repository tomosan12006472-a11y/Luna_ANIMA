from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import settings_store
from app.config import APP_PIN
from app.main import app
from app.schemas.generation import GenerateRequest


class SettingsStoreTests(unittest.TestCase):
    def test_official_colorfix_settings_are_sanitized(self) -> None:
        defaulted = settings_store.sanitize_app_settings({"official_loras": {"highres": {"enabled": True}}})
        boosted = settings_store.sanitize_app_settings({"official_loras": {"colorfix": {"enabled": True, "strength": 2}}})
        clamped = settings_store.sanitize_app_settings({"official_loras": {"colorfix": {"enabled": True, "strength": 4}}})

        self.assertIn("colorfix", defaulted["official_loras"])
        self.assertFalse(defaulted["official_loras"]["colorfix"]["enabled"])
        self.assertEqual(defaulted["official_loras"]["colorfix"]["strength"], 0.6)
        self.assertTrue(boosted["official_loras"]["colorfix"]["enabled"])
        self.assertEqual(boosted["official_loras"]["colorfix"]["strength"], 2.0)
        self.assertTrue(clamped["official_loras"]["colorfix"]["enabled"])
        self.assertEqual(clamped["official_loras"]["colorfix"]["strength"], 3.0)

    def test_turbo_restore_settings_defaults_and_sanitize(self) -> None:
        self.assertEqual(settings_store.DEFAULT_APP_SETTINGS["turbo_restore_settings"], {"steps": 32, "cfg": 4.5, "strength": 0.6})

        settings = settings_store.sanitize_app_settings(
            {
                "turbo_restore_settings": {
                    "steps": "999",
                    "cfg": "-2",
                    "strength": "bad",
                }
            }
        )

        self.assertEqual(settings["turbo_restore_settings"], {"steps": 100, "cfg": 1.0, "strength": 0.6})

        boosted = settings_store.sanitize_app_settings({"turbo_restore_settings": {"strength": 2.5}})
        clamped = settings_store.sanitize_app_settings({"turbo_restore_settings": {"strength": 9}})
        self.assertEqual(boosted["turbo_restore_settings"]["strength"], 2.5)
        self.assertEqual(clamped["turbo_restore_settings"]["strength"], 3.0)

    def test_turbo_restore_settings_migrate_from_old_turbo_off_settings(self) -> None:
        settings = settings_store.sanitize_app_settings(
            {
                "steps": 28,
                "cfg": 4.2,
                "official_loras": {
                    "turbo": {"enabled": False, "strength": 0.45},
                },
            }
        )

        self.assertEqual(settings["turbo_restore_settings"], {"steps": 28, "cfg": 4.2, "strength": 0.45})

    def test_lora_settings_preserve_strength_above_one(self) -> None:
        settings = settings_store.sanitize_app_settings(
            {
                "loras": [
                    {"name": "style/boosted.safetensors", "strength_model": 1.8, "strength_clip": 1.2},
                    {"name": "style/clamped.safetensors", "strength_model": 9, "strength_clip": 4},
                ]
            }
        )

        self.assertEqual(settings["loras"][0]["strength_model"], 1.8)
        self.assertEqual(settings["loras"][0]["strength_clip"], 1.2)
        self.assertEqual(settings["loras"][1]["strength_model"], 3.0)
        self.assertEqual(settings["loras"][1]["strength_clip"], 3.0)

    def test_turbo_restore_settings_migrate_old_turbo_on_to_non_turbo_default(self) -> None:
        for preset_applied in (True, False):
            settings = settings_store.sanitize_app_settings(
                {
                    "steps": 10,
                    "cfg": 1,
                    "official_loras": {
                        "turbo": {"enabled": True, "strength": 1, "preset_applied": preset_applied},
                    },
                }
            )

            self.assertEqual(settings["turbo_restore_settings"], settings_store.DEFAULT_APP_SETTINGS["turbo_restore_settings"])

    def test_settings_post_round_trip_preserves_turbo_restore_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            with mock.patch.object(settings_store, "SETTINGS_PATH", settings_path):
                client = TestClient(app)
                client.post("/api/login", json={"pin": APP_PIN})
                response = client.post(
                    "/api/settings",
                    json={
                        "mode": "current",
                        "settings": {
                            "steps": 10,
                            "cfg": 1,
                            "official_loras": {"turbo": {"enabled": True, "strength": 1, "preset_applied": True}},
                            "turbo_restore_settings": {"steps": 32, "cfg": 4.5, "strength": 0.6},
                        },
                    },
                )

                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["settings"]["turbo_restore_settings"], {"steps": 32, "cfg": 4.5, "strength": 0.6})
                self.assertEqual(json.loads(settings_path.read_text(encoding="utf-8"))["turbo_restore_settings"]["steps"], 32)

    def test_generate_request_ignores_turbo_restore_settings(self) -> None:
        data = GenerateRequest.model_validate({"turbo_restore_settings": {"steps": 32, "cfg": 4.5, "strength": 0.6}})

        self.assertNotIn("turbo_restore_settings", data.model_dump())

    def test_prompt_random_instruction_favorites_are_sanitized(self) -> None:
        settings = settings_store.sanitize_app_settings(
            {
                "prompt_random_instruction_favorites": [
                    {
                        "id": "fav-1",
                        "label": "水着のまま遊びを足す",
                        "instruction": "水着を維持して、小物と背景を足す",
                        "mode": "bad-mode",
                        "strength": "legacy_568",
                        "include_characters": False,
                        "use_character_motifs": True,
                    },
                    {"instruction": ""},
                    "bad",
                ]
            }
        )

        favorites = settings["prompt_random_instruction_favorites"]
        self.assertEqual(len(favorites), 1)
        self.assertEqual(favorites[0]["id"], "fav-1")
        self.assertEqual(favorites[0]["mode"], "random")
        self.assertEqual(favorites[0]["strength"], "legacy_568")
        self.assertFalse(favorites[0]["include_characters"])
        self.assertFalse(favorites[0]["use_character_motifs"])


if __name__ == "__main__":
    unittest.main()
