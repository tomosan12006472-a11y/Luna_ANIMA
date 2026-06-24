from __future__ import annotations

import unittest

from app.official_lora_presets import apply_builtin_official_lora_preset, builtin_official_lora_presets, infer_builtin_official_lora_preset_id
from app.schemas.generation import GenerateRequest
from app.settings_store import sanitize_app_settings


class OfficialLoraPresetTests(unittest.TestCase):
    def test_builtin_fast_color_preset_shape(self) -> None:
        official = apply_builtin_official_lora_preset("fast_color")

        self.assertFalse(official["highres"]["enabled"])
        self.assertTrue(official["turbo"]["enabled"])
        self.assertEqual(official["turbo"]["strength"], 1.0)
        self.assertTrue(official["turbo"]["preset_applied"])
        self.assertTrue(official["colorfix"]["enabled"])
        self.assertEqual(official["colorfix"]["strength"], 0.6)

    def test_builtin_preset_list_is_stable(self) -> None:
        ids = [item["id"] for item in builtin_official_lora_presets()]

        self.assertEqual(ids, ["off", "color_stable", "quality", "fast_preview", "fast_color", "final_quality"])

    def test_settings_preserve_optional_preset_id(self) -> None:
        settings = sanitize_app_settings({"official_lora_preset": "quality"})

        self.assertEqual(settings["official_lora_preset"], "quality")
        self.assertFalse(settings["official_loras"]["highres"]["enabled"])

    def test_infer_builtin_preset_from_official_loras(self) -> None:
        official = apply_builtin_official_lora_preset("quality")

        self.assertEqual(infer_builtin_official_lora_preset_id(official), "quality")

    def test_settings_default_old_empty_data_to_off_preset(self) -> None:
        settings = sanitize_app_settings({})

        self.assertEqual(settings["official_lora_preset"], "off")

    def test_settings_default_old_custom_loras_to_custom_preset(self) -> None:
        settings = sanitize_app_settings({"official_loras": {"colorfix": {"enabled": True, "strength": 2}}})

        self.assertEqual(settings["official_lora_preset"], "custom")
        self.assertTrue(settings["official_loras"]["colorfix"]["enabled"])
        self.assertEqual(settings["official_loras"]["colorfix"]["strength"], 1.0)
        self.assertTrue(settings["official_loras"]["turbo"]["preset_applied"])

    def test_generate_request_preserves_optional_preset_meta(self) -> None:
        data = GenerateRequest(official_lora_preset="fast_preview")

        self.assertEqual(data.model_dump()["official_lora_preset"], "fast_preview")


if __name__ == "__main__":
    unittest.main()
