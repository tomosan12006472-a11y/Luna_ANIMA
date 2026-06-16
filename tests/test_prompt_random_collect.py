from __future__ import annotations

import unittest

from app import prompt_random_collect


class PromptRandomCollectTests(unittest.TestCase):
    def test_sanitize_request_defaults_instruction_and_strength(self) -> None:
        result = prompt_random_collect.sanitize_prompt_random_collect_request({"enabled": True, "strength": "bad"})
        self.assertTrue(result["enabled"])
        self.assertEqual(result["instruction"], prompt_random_collect.DEFAULT_INSTRUCTION)
        self.assertEqual(result["strength"], "standard")
        self.assertTrue(result["include_characters"])

    def test_sanitize_request_can_disable_character_context(self) -> None:
        result = prompt_random_collect.sanitize_prompt_random_collect_request({"enabled": True, "include_characters": False})
        self.assertFalse(result["include_characters"])

    def test_normalize_items_removes_disallowed_syntax_and_existing_tags(self) -> None:
        contexts = [{"index": 0, "seed": 11, "existing_positive": "white hair, blue eyes"}]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "white_hair, blue_eyes, red_dress, <lora:test:1>, __pose__"}]},
            contexts,
        )
        self.assertEqual(result[0]["tags"], "red dress")

    def test_normalize_items_requires_one_item_per_context(self) -> None:
        contexts = [{"index": 0}, {"index": 1}]
        with self.assertRaises(ValueError):
            prompt_random_collect.normalize_prompt_random_collect_items({"items": [{"index": 0, "tags": "red dress"}]}, contexts)

    def test_normalize_items_rejects_duplicate_tag_sets(self) -> None:
        contexts = [{"index": 0}, {"index": 1}]
        with self.assertRaises(ValueError):
            prompt_random_collect.normalize_prompt_random_collect_items(
                {"items": [{"index": 0, "tags": "red dress"}, {"index": 1, "tags": "red dress"}]},
                contexts,
            )

    def test_attach_generated_item_to_each_request(self) -> None:
        requests = [{"queue_index": 0, "prompt_random_collect": {"enabled": True}}, {"queue_index": 1, "prompt_random_collect": {"enabled": True}}]
        prompt_random_collect.attach_prompt_random_collect_items(
            requests,
            {
                "instruction": "test",
                "strength": "subtle",
                "include_characters": False,
                "generated_items": [{"index": 0, "tags": "red dress"}, {"index": 1, "tags": "blue dress"}],
                "provider": {"model": "qwen"},
            },
        )
        self.assertEqual(prompt_random_collect.prompt_random_collect_tags(requests[0]), "red dress")
        self.assertEqual(prompt_random_collect.prompt_random_collect_tags(requests[1]), "blue dress")
        self.assertFalse(requests[0]["prompt_random_collect"]["include_characters"])


if __name__ == "__main__":
    unittest.main()
