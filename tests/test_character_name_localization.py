from __future__ import annotations

import re
import unittest

from app.anima_adapter import catalog
from app.favorites_store import normalize_favorites
from app.history_store import normalize_history_item
from app.payload_builder import build_prompts


BASE_REQUEST = {
    "character1": "scathach (fate)",
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

    def test_catalog_search_page_reports_total_and_offset(self) -> None:
        first = catalog.search_page("fgo", "all", 60, 0)
        second = catalog.search_page("fgo", "all", 60, 60)
        self.assertGreater(first["total"], 60)
        self.assertTrue(first["has_more"])
        self.assertEqual(len(first["items"]), 60)
        self.assertEqual(second["offset"], 60)
        self.assertNotEqual(first["items"][0]["prompt_tag"], second["items"][0]["prompt_tag"])

    def test_expanded_fate_catalog_search_matches_added_tag(self) -> None:
        items = catalog.search("kashin koji", "all", 5)
        self.assertTrue(items)
        self.assertEqual(items[0]["prompt_tag"], "kashin koji (fate)")
        self.assertEqual(items[0]["kind"], "custom")

    def test_expanded_danbooru_catalog_search_matches_game_tags(self) -> None:
        cases = [
            ("スタレ", "firefly (honkai: star rail)", "ホタル（スターレイル）"),
            ("ゼンゼロ", "yixuan (zenless zone zero)", "Yixuan（ゼンゼロ）"),
            ("sandrone", "sandrone (genshin impact)", "サンドローネ（原神）"),
        ]
        for query, prompt_tag, display_name in cases:
            with self.subTest(query=query):
                items = catalog.search(query, "all", 20)
                match = next((item for item in items if item["prompt_tag"] == prompt_tag), None)
                self.assertIsNotNone(match)
                self.assertEqual(match["kind"], "custom")
                self.assertEqual(match["display_name_ja"], display_name)

    def test_expanded_danbooru_catalog_prompt_uses_prompt_safe_names(self) -> None:
        cases = [
            (
                "firefly (honkai: star rail)",
                "firefly \\(honkai: star rail\\)",
                "Firefly from Honkai: Star Rail",
                "ホタル（スターレイル）",
            ),
            (
                "yixuan (zenless zone zero)",
                "yixuan \\(zenless zone zero\\)",
                "Yixuan from Zenless Zone Zero",
                "Yixuan（ゼンゼロ）",
            ),
            (
                "sandrone (genshin impact)",
                "sandrone \\(genshin impact\\)",
                "Sandrone from Genshin Impact",
                "サンドローネ（原神）",
            ),
        ]
        for character, prompt_tag, prompt_name, display_name in cases:
            with self.subTest(character=character):
                request = dict(BASE_REQUEST)
                request["character1"] = character
                prompts = build_prompts(request)
                self.assertIn(prompt_tag, prompts["positive"])
                self.assertIn(prompt_name, prompts["positive"])
                self.assertNotRegex(prompts["positive"], re.compile(r"[\u3400-\u9fff]"))
                self.assertEqual(prompts["characters"], [display_name])

    def test_legacy_favorite_display_name_uses_current_catalog(self) -> None:
        data = normalize_favorites(
            {
                "characters": [
                    {
                        "source": "wai_characters",
                        "id": "legacy_scathach",
                        "name": "斯卡哈（Fate）",
                        "display_name": "斯卡哈（Fate）",
                        "prompt_tag": "scathach (fate)",
                    }
                ]
            }
        )
        self.assertEqual(data["characters"][0]["name"], "スカサハ（Fate）")
        self.assertEqual(data["characters"][0]["display_name"], "スカサハ（Fate）")

    def test_legacy_history_character_display_name_uses_current_catalog(self) -> None:
        item = normalize_history_item(
            {
                "id": "legacy_history",
                "characters": [
                    {
                        "slot": 1,
                        "source": "saa_csv",
                        "id": "斯卡哈（Fate）",
                        "display_name": "斯卡哈（Fate）",
                        "prompt_tag": "scathach (fate)",
                    }
                ],
                "character_names": ["斯卡哈（Fate）"],
            }
        )
        self.assertEqual(item["characters"][0]["display_name"], "スカサハ（Fate）")
        self.assertEqual(item["characters"][0]["display_name_ja"], "スカサハ（Fate）")
        self.assertEqual(item["characters"][0]["display_name_original"], "斯卡哈（Fate）")
        self.assertEqual(item["character_names"], ["スカサハ（Fate）"])

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
