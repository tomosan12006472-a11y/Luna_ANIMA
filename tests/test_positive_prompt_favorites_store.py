from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app import positive_prompt_favorites_store as store


class PositivePromptFavoritesStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "positive_prompt_favorites.json"
        self._original_path = store.FAVORITES_PATH
        store.FAVORITES_PATH = self.path

    def tearDown(self) -> None:
        store.FAVORITES_PATH = self._original_path
        self._tmp.cleanup()

    def write_payload(self, items: list[dict[str, object]]) -> None:
        self.path.write_text(json.dumps({"version": 1, "app_scope": store.APP_SCOPE, "items": items}, ensure_ascii=False), encoding="utf-8")

    def broken_backups(self) -> list[Path]:
        return list(self.path.parent.glob(f"{self.path.stem}.broken_*{self.path.suffix}"))

    def test_load_retries_transient_read_failure_without_backup(self) -> None:
        self.write_payload([{"id": "fav_1", "title": "First", "prompt": "blue dress"}])
        original_read_text = Path.read_text
        calls = 0

        def flaky_read_text(path: Path, *args: object, **kwargs: object) -> str:
            nonlocal calls
            if path == self.path and calls == 0:
                calls += 1
                raise OSError("temporary read failure")
            calls += 1
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(store.time, "sleep", lambda _: None), mock.patch.object(Path, "read_text", flaky_read_text):
            payload = store.list_positive_prompt_favorites()

        self.assertEqual(payload["items"][0]["id"], "fav_1")
        self.assertEqual(calls, 2)
        self.assertEqual(self.broken_backups(), [])

    def test_mutation_stops_when_existing_payload_stays_unreadable(self) -> None:
        self.path.write_text("{", encoding="utf-8")
        original_text = self.path.read_text(encoding="utf-8")

        with mock.patch.object(store.time, "sleep", lambda _: None):
            with self.assertRaises(RuntimeError):
                store.add_positive_prompt_favorite({"prompt": "new prompt"})

        self.assertEqual(self.path.read_text(encoding="utf-8"), original_text)
        self.assertEqual(self.broken_backups(), [])


if __name__ == "__main__":
    unittest.main()
