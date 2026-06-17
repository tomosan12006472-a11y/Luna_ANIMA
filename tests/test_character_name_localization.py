from __future__ import annotations

import re
import unittest

from app.anima_adapter import catalog
from app.payload_builder import build_prompts


BASE_REQUEST = {
    "character1": "斯卡哈（Fate）",
    "character2": "None",
    "character3": "None",
    "original_character": "None",
    "seed": 12345,
    "rating": "safe",
    "quality_preset": "standard",
    "meta_prompt": "anime illustration",
    "year_prompt": "",
    "outfit_prompt": "",
    "expression_prompt": "",
    "pose_prompt": "",
    "background_prompt": "",
    "lighting_prompt": "",
    "camera_prompt": "",
    "positive_prompt": "",
    "common_prompt": "",
    "negative_prompt": "",
    "negative_prompt_mode": "custom",
    "negative_preset": "anima_recommended",
    "prompt_ban": "",
    "dynamic_prompt": {"enabled": False},
}


class CharacterNameLocalizationTest(unittest.TestCase):
    def test_anima_generated_positive_uses_prompt_safe_character_name(self) -> None:
        prompts = build_prompts(dict(BASE_REQUEST))
        self.assertIn("scathach \\(fate\\)", prompts["positive"])
        self.assertIn("Scathach from Fate", prompts["positive"])
        self.assertNotRegex(prompts["positive"], re.compile(r"[\u3400-\u9fff]"))
        self.assertEqual(prompts["characters"], ["スカサハ（Fate）"])

    def test_quality_prompt_override_replaces_default_quality_tags(self) -> None:
        request = dict(BASE_REQUEST)
        request["quality_prompt_overrides"] = {"standard": "custom quality tag, crisp detail"}
        prompts = build_prompts(request)
        self.assertIn("custom quality tag, crisp detail", prompts["positive"])
        self.assertNotIn("masterpiece, best quality, score_7", prompts["positive"])

    def test_rating_prompt_override_replaces_default_rating_tag(self) -> None:
        request = dict(BASE_REQUEST)
        request["rating_prompt_overrides"] = {"safe": "family friendly"}
        prompts = build_prompts(request)
        self.assertIn("family friendly", prompts["positive"])
        self.assertNotIn(", safe,", f", {prompts['positive']},")

    def test_catalog_search_matches_japanese_display_name(self) -> None:
        items = catalog.search("スカサハ", "all", 5)
        self.assertTrue(items)
        self.assertEqual(items[0]["prompt_tag"], "scathach (fate)")
        self.assertEqual(items[0]["display_name_ja"], "スカサハ（Fate）")

    def test_external_character_catalog_search_and_prompt(self) -> None:
        items = catalog.search("光の戦士", "all", 5)
        self.assertTrue(items)
        self.assertEqual(items[0]["kind"], "custom")
        self.assertEqual(items[0]["prompt_tag"], "warrior of light (ff14)")
        self.assertEqual(items[0]["display_name_ja"], "光の戦士（FF14）")

        request = dict(BASE_REQUEST)
        request["character1"] = "warrior of light (ff14)"
        prompts = build_prompts(request)
        self.assertIn("warrior of light \\(ff14\\)", prompts["positive"])
        self.assertNotRegex(prompts["positive"], re.compile(r"[\u3400-\u9fff]"))
        self.assertEqual(prompts["characters"], ["光の戦士（FF14）"])


if __name__ == "__main__":
    unittest.main()
