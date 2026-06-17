from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app import prompt_dictionary_store


class PromptDictionaryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name) / "dictionary"
        self.data_dir.mkdir()
        self._candidate_patch = mock.patch.object(prompt_dictionary_store, "_candidate_data_dirs", lambda: [self.data_dir])
        self._candidate_patch.start()
        prompt_dictionary_store._reset_cache_for_tests()

    def tearDown(self) -> None:
        self._candidate_patch.stop()
        prompt_dictionary_store._reset_cache_for_tests()
        self._tmp.cleanup()

    def write_main(self, rows: list[dict[str, str]]) -> None:
        header = ["tag", "display_tag", "ja", "description", "aliases", "search_aliases", "related_tags", "post_count", "importance"]
        lines = ["\t".join(header)]
        for row in rows:
            lines.append("\t".join(row.get(field, "") for field in header))
        (self.data_dir / prompt_dictionary_store.MAIN_TSV).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_extra(self, rows: list[dict[str, str]]) -> None:
        header = ["tag", "display_tag", "ja", "description", "aliases", "search_aliases", "related_tags", "post_count", "importance"]
        lines = ["\t".join(header)]
        for row in rows:
            lines.append("\t".join(row.get(field, "") for field in header))
        (self.data_dir / prompt_dictionary_store.EXTRA_TSV).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_external_tsv_update_invalidates_cache(self) -> None:
        self.write_main([{"tag": "blue_eyes", "display_tag": "blue eyes", "ja": "青い目", "post_count": "100"}])

        first = prompt_dictionary_store.search_prompt_dictionary("blue eyes")
        self.assertEqual([item["tag"] for item in first["items"]], ["blue_eyes"])

        self.write_main(
            [
                {"tag": "blue_eyes", "display_tag": "blue eyes", "ja": "青い目", "post_count": "100"},
                {"tag": "red dress", "display_tag": "red dress", "ja": "赤いドレス", "post_count": "80"},
            ]
        )

        updated = prompt_dictionary_store.search_prompt_dictionary("red dress")
        self.assertEqual([item["tag"] for item in updated["items"]], ["red dress"])
        self.assertTrue(updated["available"])
        self.assertEqual(updated["entry_count"], 2)

    def test_extra_tsv_appearance_invalidates_cache(self) -> None:
        self.write_main([{"tag": "blue_eyes", "display_tag": "blue eyes", "ja": "青い目", "post_count": "100"}])
        self.assertEqual(prompt_dictionary_store.search_prompt_dictionary("azure")["items"], [])

        self.write_extra([{"tag": "blue_eyes", "search_aliases": "azure gaze"}])

        updated = prompt_dictionary_store.search_prompt_dictionary("azure")
        self.assertEqual([item["tag"] for item in updated["items"]], ["blue_eyes"])

    def test_dictionary_file_can_appear_after_missing_cache(self) -> None:
        missing = prompt_dictionary_store.prompt_dictionary_status()
        self.assertFalse(missing["available"])
        self.assertEqual(missing["entry_count"], 0)

        self.write_main([{"tag": "silver hair", "display_tag": "silver hair", "ja": "銀髪", "post_count": "50"}])

        found = prompt_dictionary_store.search_prompt_dictionary("銀髪")
        self.assertTrue(found["available"])
        self.assertEqual([item["tag"] for item in found["items"]], ["silver hair"])

    def test_reload_failure_keeps_previous_cache_and_recovers(self) -> None:
        self.write_main([{"tag": "blue_eyes", "display_tag": "blue eyes", "ja": "青い目", "post_count": "100"}])
        first = prompt_dictionary_store.search_prompt_dictionary("blue eyes")
        self.assertEqual([item["tag"] for item in first["items"]], ["blue_eyes"])

        self.write_main(
            [
                {"tag": "blue_eyes", "display_tag": "blue eyes", "ja": "青い目", "post_count": "100"},
                {"tag": "green hair", "display_tag": "green hair", "ja": "緑髪", "post_count": "80"},
            ]
        )

        with mock.patch.object(prompt_dictionary_store, "_read_tsv", side_effect=RuntimeError("partial write")):
            stale = prompt_dictionary_store.search_prompt_dictionary("green hair")

        self.assertEqual(stale["items"], [])
        self.assertEqual(stale["entry_count"], 1)
        self.assertIn("prompt dictionary reload failed", stale["warning"])

        recovered = prompt_dictionary_store.search_prompt_dictionary("green hair")
        self.assertIsNone(recovered["warning"])
        self.assertEqual([item["tag"] for item in recovered["items"]], ["green hair"])


if __name__ == "__main__":
    unittest.main()
