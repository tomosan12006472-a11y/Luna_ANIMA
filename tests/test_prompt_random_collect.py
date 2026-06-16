from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app import history_store, prompt_random_collect


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

    def test_history_summary_preserves_generated_tags_for_reuse_strip(self) -> None:
        summary = history_store._prompt_random_collect_summary(
            {
                "prompt_random_collect": {
                    "enabled": True,
                    "instruction": "test",
                    "strength": "subtle",
                    "include_characters": False,
                    "generated_item": {"index": 0, "tags": "red dress"},
                    "provider": {"model": "qwen"},
                }
            }
        )
        self.assertIsNotNone(summary)
        self.assertEqual(summary["generated_tags"], "red dress")
        self.assertFalse(summary["include_characters"])

    def test_history_detail_enriches_raw_prompt_from_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload_path = Path(directory) / "payload.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "request": {
                            "positive_prompt": "raw positive",
                            "negative_prompt_raw": "raw negative",
                            "prompt_random_collect": {
                                "enabled": True,
                                "generated_tags": "blue dress",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            item = {"id": "test", "payload_path": str(payload_path), "positive": "masterpiece, raw positive, blue dress"}
            enriched = history_store.enrich_history_item_from_payload(item)
        self.assertEqual(enriched["positive_prompt"], "raw positive")
        self.assertEqual(enriched["negative_prompt_raw"], "raw negative")
        self.assertEqual(enriched["prompt_random_collect"]["generated_tags"], "blue dress")


if __name__ == "__main__":
    unittest.main()
