from __future__ import annotations

from types import SimpleNamespace
import unittest

from app import prompt_converter


class PromptConverterTests(unittest.TestCase):
    def test_sanitize_settings_normalizes_provider_and_limits(self) -> None:
        settings = prompt_converter.sanitize_prompt_converter_settings(
            {
                "provider": "llama",
                "base_url": "http://127.0.0.1:8080",
                "model": "",
                "timeout_sec": 999,
                "temperature": -1,
                "max_tokens": 99999,
                "auto_start": {"enabled": True, "health_timeout_sec": 1},
            }
        )
        self.assertEqual(settings["provider"], "llama.cpp")
        self.assertEqual(settings["base_url"], "http://127.0.0.1:8080/v1")
        self.assertEqual(settings["model"], "auto")
        self.assertEqual(settings["timeout_sec"], 300.0)
        self.assertEqual(settings["temperature"], 0.0)
        self.assertEqual(settings["max_tokens"], 4096)
        self.assertEqual(settings["auto_start"]["health_timeout_sec"], 3.0)

    def test_normalize_tag_prompt_removes_disallowed_syntax_and_dedupes(self) -> None:
        result = prompt_converter.normalize_tag_prompt(
            "<lora:foo:1>, __pose__, score_9, score_8_up, white_hair, full_body, (blue_eyes:1.1), source_anime",
            "score_9, white hair",
        )
        self.assertEqual(result, "score_8_up, full body, (blue eyes:1.1), source anime")

    def test_normalize_tag_prompt_keeps_score_underscore_only(self) -> None:
        result = prompt_converter.normalize_tag_prompt("white_hair, white hair, score_7_up, score_7_up")
        self.assertEqual(result, "white hair, score_7_up")

    def test_normalize_natural_prompt_removes_lora_and_wildcards(self) -> None:
        result = prompt_converter.normalize_natural_prompt("  A girl with __pose__ and <lora:test:1> white hair.  ")
        self.assertEqual(result, "A girl with and white hair.")

    def test_parse_json_object_prefers_last_fenced_json(self) -> None:
        result = prompt_converter._parse_json_object('notes {"tags_en": "draft"}\n```json\n{"natural_en": "final", "tags_en": "white dress"}\n```')
        self.assertEqual(result["natural_en"], "final")
        self.assertEqual(result["tags_en"], "white dress")

    def test_user_prompt_excludes_existing_positive_text(self) -> None:
        payload = prompt_converter._user_prompt("白いワンピース", "tags", "Sesshoin Kiara, Fate/Grand Order")
        self.assertIn("白いワンピース", payload)
        self.assertNotIn("Sesshoin Kiara", payload)
        self.assertNotIn("existing_positive", payload)

    def test_character_warning_reports_catalog_match(self) -> None:
        entry = SimpleNamespace(display_name="Scathach", id="", prompt_tag="scathach (fate), purple hair", trigger_words=[])
        warnings = prompt_converter.character_warnings("Scathachを夕焼けの海辺で", "", "purple hair", [entry])
        self.assertEqual(warnings[0]["code"], "character_match")
        self.assertEqual(warnings[0]["characters"], ["Scathach"])


if __name__ == "__main__":
    unittest.main()
