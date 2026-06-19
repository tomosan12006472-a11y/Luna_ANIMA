from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app import _shared_utils
from app import favorites_store
from app import history_flags_store
from app import positive_prompt_favorites_store
from app import recipes_store
from app.storage.json_store import JsonStoreReadError


class LightweightJsonStoreMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

        self._favorites_path = favorites_store.FAVORITES_PATH
        self._positive_path = positive_prompt_favorites_store.FAVORITES_PATH
        self._recipes_path = recipes_store.RECIPES_PATH
        self._flags_path = history_flags_store.FLAGS_PATH

        favorites_store.FAVORITES_PATH = self.root / "favorites.json"
        positive_prompt_favorites_store.FAVORITES_PATH = self.root / "positive_prompt_favorites.json"
        recipes_store.RECIPES_PATH = self.root / "recipes.json"
        history_flags_store.FLAGS_PATH = self.root / "history_flags.json"

    def tearDown(self) -> None:
        favorites_store.FAVORITES_PATH = self._favorites_path
        positive_prompt_favorites_store.FAVORITES_PATH = self._positive_path
        recipes_store.RECIPES_PATH = self._recipes_path
        history_flags_store.FLAGS_PATH = self._flags_path
        self._tmp.cleanup()

    def test_favorites_store_shape_and_updates(self) -> None:
        self.assertEqual(favorites_store.load_favorites(), {"characters": [], "original_characters": []})

        entry = favorites_store.catalog.wai[0]
        status, favorite, payload = favorites_store.add_favorite(
            {"source": "wai_characters", "display_name": entry.display_name}
        )

        self.assertEqual(status, "created")
        self.assertEqual(favorite["source"], "wai_characters")
        self.assertEqual(favorite["display_name"], entry.display_name)
        self.assertEqual(favorite["prompt_tag"], entry.prompt_tag)
        self.assertEqual(favorite["use_count"], 0)
        self.assertIsNone(favorite["last_used_at"])
        self.assertEqual(payload["characters"][0]["id"], favorite["id"])

        used = favorites_store.mark_favorite_used("wai_characters", favorite["id"])
        self.assertIsNotNone(used)
        self.assertEqual(used["use_count"], 1)
        self.assertTrue(used["last_used_at"])

        localized = favorites_store.localized_favorites(favorites_store.load_favorites())
        self.assertIn("characters", localized)
        self.assertEqual(localized["characters"][0]["id"], favorite["id"])

        removed, payload = favorites_store.remove_favorite("wai_characters", favorite["id"])
        self.assertTrue(removed)
        self.assertEqual(payload["characters"], [])

    def test_favorites_store_unreadable_update_does_not_overwrite(self) -> None:
        favorites_store.FAVORITES_PATH.write_text("{", encoding="utf-8")
        original = favorites_store.FAVORITES_PATH.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                favorites_store.remove_favorite("wai_characters", "fav_1")

        self.assertEqual(favorites_store.FAVORITES_PATH.read_text(encoding="utf-8"), original)

    def test_positive_prompt_favorites_shape_and_updates(self) -> None:
        self.assertEqual(
            positive_prompt_favorites_store.list_positive_prompt_favorites(),
            {"version": 1, "app_scope": "anima", "items": []},
        )

        item = positive_prompt_favorites_store.add_positive_prompt_favorite(
            {"title": "Blue", "prompt": "blue dress", "tags": "dress, blue", "note": "keeper"}
        )
        self.assertEqual(item["title"], "Blue")
        self.assertEqual(item["prompt"], "blue dress")
        self.assertEqual(item["tags"], ["dress", "blue"])
        self.assertTrue(item["favorite"])
        self.assertEqual(item["use_count"], 0)

        updated = positive_prompt_favorites_store.update_positive_prompt_favorite(
            item["id"],
            {"title": "Blue alt", "tags": ["blue", "blue", "dress"], "favorite": False},
        )
        self.assertEqual(updated["title"], "Blue alt")
        self.assertEqual(updated["tags"], ["blue", "dress"])
        self.assertFalse(updated["favorite"])

        used = positive_prompt_favorites_store.mark_positive_prompt_favorite_used(item["id"])
        self.assertEqual(used["use_count"], 1)
        self.assertTrue(used["last_used_at"])

        self.assertTrue(positive_prompt_favorites_store.delete_positive_prompt_favorite(item["id"]))
        self.assertEqual(positive_prompt_favorites_store.list_positive_prompt_favorites()["items"], [])

    def test_positive_prompt_favorites_unreadable_update_does_not_overwrite(self) -> None:
        positive_prompt_favorites_store.FAVORITES_PATH.write_text("{", encoding="utf-8")
        original = positive_prompt_favorites_store.FAVORITES_PATH.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                positive_prompt_favorites_store.add_positive_prompt_favorite({"prompt": "new prompt"})

        self.assertEqual(positive_prompt_favorites_store.FAVORITES_PATH.read_text(encoding="utf-8"), original)

    def test_recipes_store_shape_and_updates(self) -> None:
        self.assertEqual(recipes_store.list_recipes(), {"version": 1, "app_scope": "anima", "items": []})

        item = recipes_store.add_recipe("Daily", "short summary", {"positive_prompt": "blue dress"})
        self.assertEqual(item["name"], "Daily")
        self.assertEqual(item["summary"], "short summary")
        self.assertEqual(item["request"], {"positive_prompt": "blue dress"})
        self.assertEqual(item["use_count"], 0)

        used = recipes_store.mark_recipe_used(item["id"])
        self.assertEqual(used["use_count"], 1)
        self.assertTrue(used["last_used_at"])

        self.assertTrue(recipes_store.delete_recipe(item["id"]))
        self.assertEqual(recipes_store.list_recipes()["items"], [])

    def test_recipes_store_unreadable_update_does_not_overwrite(self) -> None:
        recipes_store.RECIPES_PATH.write_text("{", encoding="utf-8")
        original = recipes_store.RECIPES_PATH.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                recipes_store.add_recipe("Daily", "summary", {"positive_prompt": "blue dress"})

        self.assertEqual(recipes_store.RECIPES_PATH.read_text(encoding="utf-8"), original)

    def test_history_flags_shape_attach_filter_and_summary(self) -> None:
        flags = history_flags_store.update_history_flags(
            "hist_1",
            {"favorite": True, "post_candidate": True, "hidden": False, "tags": ["keeper"], "ignored": True},
        )

        self.assertTrue(flags["favorite"])
        self.assertTrue(flags["post_candidate"])
        self.assertFalse(flags["hidden"])
        self.assertEqual(flags["tags"], ["keeper"])
        self.assertIn("updated_at", flags)

        item = {"id": "hist_1", "image_path": "image.png"}
        attached = history_flags_store.attach_flags_to_item(item)
        self.assertEqual(attached["image_path"], "image.png")
        self.assertTrue(attached["flags"]["favorite"])

        items = history_flags_store.attach_flags_to_items([{"id": "hist_1"}, {"id": "hist_2"}])
        self.assertEqual(len(history_flags_store.filter_items_by_flags(items, "favorite")), 1)
        self.assertEqual(len(history_flags_store.filter_items_by_flags(items, "post_candidate")), 1)
        self.assertEqual(
            history_flags_store.flag_summary(items),
            {"total": 2, "favorites": 1, "post_candidates": 1, "hidden": 0},
        )

        stored = json.loads(history_flags_store.FLAGS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(stored["schema_version"], 1)
        self.assertEqual(stored["app_scope"], "anima")
        self.assertIn("hist_1", stored["items"])

    def test_history_flags_unreadable_update_does_not_overwrite(self) -> None:
        history_flags_store.FLAGS_PATH.write_text("{", encoding="utf-8")
        original = history_flags_store.FLAGS_PATH.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                history_flags_store.update_history_flags("hist_1", {"favorite": True})

        self.assertEqual(history_flags_store.FLAGS_PATH.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
