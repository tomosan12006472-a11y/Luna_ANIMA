from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app import _shared_utils
from app import favorites_store
from app import recipes_store
from app import settings_store
from app._shared_utils import JsonStoreReadError


class JsonStoreReadFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.favorites_path = self.root / "favorites.json"
        self.recipes_path = self.root / "recipes.json"
        self.settings_path = self.root / "settings.json"
        self._original_favorites_path = favorites_store.FAVORITES_PATH
        self._original_recipes_path = recipes_store.RECIPES_PATH
        self._original_settings_path = settings_store.SETTINGS_PATH
        favorites_store.FAVORITES_PATH = self.favorites_path
        recipes_store.RECIPES_PATH = self.recipes_path
        settings_store.SETTINGS_PATH = self.settings_path

    def tearDown(self) -> None:
        favorites_store.FAVORITES_PATH = self._original_favorites_path
        recipes_store.RECIPES_PATH = self._original_recipes_path
        settings_store.SETTINGS_PATH = self._original_settings_path
        self._tmp.cleanup()

    def broken_backups(self, path: Path) -> list[Path]:
        return list(path.parent.glob(f"{path.stem}.broken_*{path.suffix}"))

    def test_character_favorites_retry_transient_read_failure(self) -> None:
        self.favorites_path.write_text(
            json.dumps(
                {
                    "characters": [
                        {
                            "source": "wai_characters",
                            "id": "fav_1",
                            "display_name": "Saber",
                            "prompt_tag": "saber (fate)",
                        }
                    ],
                    "original_characters": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        original_read_text = Path.read_text
        calls = 0

        def flaky_read_text(path: Path, *args: object, **kwargs: object) -> str:
            nonlocal calls
            if path == self.favorites_path and calls == 0:
                calls += 1
                raise OSError("temporary read failure")
            calls += 1
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None), mock.patch.object(Path, "read_text", flaky_read_text):
            payload = favorites_store.load_favorites()

        self.assertEqual(payload["characters"][0]["id"], "fav_1")
        self.assertEqual(calls, 2)
        self.assertEqual(self.broken_backups(self.favorites_path), [])

    def test_character_favorites_mutation_stops_when_payload_stays_unreadable(self) -> None:
        self.favorites_path.write_text("{", encoding="utf-8")
        original_text = self.favorites_path.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                favorites_store.remove_favorite("wai_characters", "fav_1")

        self.assertEqual(self.favorites_path.read_text(encoding="utf-8"), original_text)
        self.assertEqual(self.broken_backups(self.favorites_path), [])

    def test_recipes_mutation_stops_when_payload_stays_unreadable(self) -> None:
        self.recipes_path.write_text("{", encoding="utf-8")
        original_text = self.recipes_path.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                recipes_store.add_recipe("test", "summary", {"positive_prompt": "blue dress"})

        self.assertEqual(self.recipes_path.read_text(encoding="utf-8"), original_text)
        self.assertEqual(self.broken_backups(self.recipes_path), [])

    def test_settings_save_stops_when_existing_file_stays_unreadable(self) -> None:
        self.settings_path.write_text("{", encoding="utf-8")
        original_text = self.settings_path.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                settings_store.save_app_settings({"width": 768})

        self.assertEqual(self.settings_path.read_text(encoding="utf-8"), original_text)
        self.assertEqual(self.broken_backups(self.settings_path), [])


if __name__ == "__main__":
    unittest.main()
