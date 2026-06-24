from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app import _shared_utils
from app import original_characters
from app._shared_utils import JsonStoreReadError


class OriginalCharactersStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "original_characters.json"
        self._original_path = original_characters.ORIGINAL_CHARACTERS_PATH
        self._original_defaults = original_characters.DEFAULT_ORIGINAL_CHARACTERS
        original_characters.ORIGINAL_CHARACTERS_PATH = self.path
        original_characters.DEFAULT_ORIGINAL_CHARACTERS = []

    def tearDown(self) -> None:
        original_characters.ORIGINAL_CHARACTERS_PATH = self._original_path
        original_characters.DEFAULT_ORIGINAL_CHARACTERS = self._original_defaults
        self._tmp.cleanup()

    def write_payload(self, payload: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_load_user_original_characters_accepts_legacy_list_payload(self) -> None:
        self.write_payload(
            [
                {
                    "display_name": "Luna",
                    "trigger_words": "luna girl, silver hair",
                    "identity_prompt": "gentle moonlit heroine",
                }
            ]
        )

        items = original_characters.load_user_original_characters()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "luna")
        self.assertEqual(items[0]["display_name"], "Luna")
        self.assertEqual(items[0]["prompt_tag"], "luna girl, silver hair")
        self.assertEqual(items[0]["trigger_words"], ["luna girl", "silver hair"])

    def test_upsert_original_character_preserves_existing_items(self) -> None:
        self.write_payload(
            {
                "schema_version": 1,
                "items": [
                    {
                        "id": "luna",
                        "display_name": "Luna",
                        "positive_tags": ["luna girl"],
                    }
                ],
            }
        )

        created = original_characters.upsert_original_character(
            {
                "display_name": "Mira",
                "positive_tags": ["mira knight"],
                "negative_guard": "avoid armor mistakes",
            }
        )
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        stored_ids = [item["id"] for item in stored["items"]]

        self.assertEqual(created["id"], "mira")
        self.assertEqual(stored["schema_version"], 1)
        self.assertIn("updated_at", stored)
        self.assertEqual(stored_ids, ["luna", "mira"])
        self.assertEqual(stored["items"][1]["negative_guard"], "avoid armor mistakes")

    def test_upsert_original_character_does_not_overwrite_unreadable_payload(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{", encoding="utf-8")
        original_text = self.path.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                original_characters.upsert_original_character(
                    {"display_name": "Mira", "positive_tags": ["mira knight"]}
                )

        self.assertEqual(self.path.read_text(encoding="utf-8"), original_text)

    def test_load_user_original_characters_retries_transient_read_failure(self) -> None:
        self.write_payload(
            {
                "schema_version": 1,
                "items": [{"display_name": "Luna", "positive_tags": ["luna girl"]}],
            }
        )
        original_read_text = Path.read_text
        calls = 0

        def flaky_read_text(path: Path, *args: object, **kwargs: object) -> str:
            nonlocal calls
            if path == self.path and calls == 0:
                calls += 1
                raise OSError("temporary read failure")
            calls += 1
            return original_read_text(path, *args, **kwargs)

        with (
            mock.patch.object(_shared_utils.time, "sleep", lambda _: None),
            mock.patch.object(Path, "read_text", flaky_read_text),
        ):
            items = original_characters.load_user_original_characters()

        self.assertEqual(items[0]["id"], "luna")
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
