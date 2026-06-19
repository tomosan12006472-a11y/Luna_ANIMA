from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from PIL import Image

from app import history_store
from app.storage.json_store import JsonStoreReadError


class HistoryJsonStoreMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.history_dir = self.root / "history"
        self.image_dir = self.root / "images"
        self.thumbnail_dir = self.root / "thumbnails"
        self.small_thumbnail_dir = self.root / "thumbnails_small"
        self.public_dir = self.root / "public"
        for path in [self.history_dir, self.image_dir, self.thumbnail_dir, self.small_thumbnail_dir, self.public_dir]:
            path.mkdir(parents=True, exist_ok=True)

        self._original_history_dir = history_store.HISTORY_DIR
        self._original_image_dir = history_store.IMAGE_DIR
        self._original_thumbnail_dir = history_store.THUMBNAIL_DIR
        self._original_small_thumbnail_dir = history_store.SMALL_THUMBNAIL_DIR
        self._original_public_dir = history_store.PUBLIC_DIR

        history_store.HISTORY_DIR = self.history_dir
        history_store.IMAGE_DIR = self.image_dir
        history_store.THUMBNAIL_DIR = self.thumbnail_dir
        history_store.SMALL_THUMBNAIL_DIR = self.small_thumbnail_dir
        history_store.PUBLIC_DIR = self.public_dir
        history_store._reset_history_cache_for_tests()

    def tearDown(self) -> None:
        history_store.HISTORY_DIR = self._original_history_dir
        history_store.IMAGE_DIR = self._original_image_dir
        history_store.THUMBNAIL_DIR = self._original_thumbnail_dir
        history_store.SMALL_THUMBNAIL_DIR = self._original_small_thumbnail_dir
        history_store.PUBLIC_DIR = self._original_public_dir
        history_store._reset_history_cache_for_tests()
        self._tmp.cleanup()

    def image_data_url(self) -> str:
        buffer = BytesIO()
        Image.new("RGB", (16, 16), (20, 80, 140)).save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def write_raw_history(self, history_id: str, payload: object) -> Path:
        path = self.history_dir / f"{history_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def write_pending_history(self, history_id: str = "pending-1") -> Path:
        return self.write_raw_history(
            history_id,
            {
                "id": history_id,
                "status": "queued",
                "created_at": "2026-06-18T09:00:00",
                "updated_at": "2026-06-18T09:00:00",
                "image_path": None,
                "thumbnail_path": None,
                "prompt_id": "prompt-old",
                "queue": {
                    "status": "queued",
                    "prompt_id": "prompt-old",
                    "submitted_at": "2026-06-18T09:00:00",
                    "last_checked_at": None,
                    "completed_at": None,
                    "error": None,
                },
                "custom_field": {"keep": True},
            },
        )

    def test_load_history_item_missing_returns_none(self) -> None:
        self.assertIsNone(history_store.load_history_item("missing"))

    def test_load_history_item_strict_raises_on_unreadable_json(self) -> None:
        path = self.history_dir / "broken.json"
        path.write_text("{", encoding="utf-8")

        with self.assertRaises(JsonStoreReadError):
            history_store.load_history_item("broken", strict=True)

        self.assertIsNone(history_store.load_history_item("broken"))
        self.assertEqual(path.read_text(encoding="utf-8"), "{")

    def test_complete_pending_history_item_does_not_overwrite_unreadable_json(self) -> None:
        path = self.history_dir / "pending-1.json"
        path.write_text("{", encoding="utf-8")
        original_text = path.read_text(encoding="utf-8")
        result = SimpleNamespace(image_data_url=self.image_data_url(), prompt_id="prompt-new")

        with self.assertRaises(JsonStoreReadError):
            history_store.complete_pending_history_item("pending-1", result)

        self.assertEqual(path.read_text(encoding="utf-8"), original_text)

    def test_update_pending_history_status_does_not_overwrite_unreadable_json(self) -> None:
        path = self.history_dir / "pending-1.json"
        path.write_text("{", encoding="utf-8")
        original_text = path.read_text(encoding="utf-8")

        with self.assertRaises(JsonStoreReadError):
            history_store.update_pending_history_status("pending-1", "failed", "queue sync failed")

        self.assertEqual(path.read_text(encoding="utf-8"), original_text)

    def test_copy_public_image_does_not_overwrite_unreadable_json(self) -> None:
        source = self.root / "source.png"
        Image.new("RGB", (320, 180), (20, 30, 40)).save(source)
        path = self.history_dir / "frame-1.json"
        path.write_text("{", encoding="utf-8")
        original_text = path.read_text(encoding="utf-8")

        with self.assertRaises(JsonStoreReadError):
            history_store.copy_public_image({"id": "frame-1", "image_path": str(source)}, {"enabled": False})

        self.assertEqual(path.read_text(encoding="utf-8"), original_text)

    def test_complete_pending_history_item_preserves_shape(self) -> None:
        self.write_pending_history()
        result = SimpleNamespace(image_data_url=self.image_data_url(), prompt_id="prompt-new")

        completed = history_store.complete_pending_history_item("pending-1", result)

        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["prompt_id"], "prompt-new")
        self.assertEqual(completed["queue"]["status"], "completed")
        self.assertIsNone(completed["queue"]["error"])
        self.assertTrue(Path(completed["image_path"]).exists())
        self.assertTrue(Path(completed["thumbnail_path"]).exists())
        stored = json.loads((self.history_dir / "pending-1.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["custom_field"], {"keep": True})
        self.assertEqual(stored["queue"]["completed_at"], completed["queue"]["completed_at"])

    def test_public_save_preserves_history_shape(self) -> None:
        source = self.root / "source.png"
        Image.new("RGB", (320, 180), (20, 30, 40)).save(source)
        history_store.save_history_item(
            {
                "id": "frame-1",
                "created_at": "2026-06-18T09:00:00",
                "status": "completed",
                "image_path": str(source),
                "thumbnail_path": str(source),
                "public_save": {"saved": False},
                "watermark": {"applied": False},
                "custom_field": {"keep": True},
            }
        )
        item = history_store.load_history_item("frame-1")
        self.assertIsNotNone(item)

        public_save = history_store.copy_public_image(item or {}, {"enabled": False})

        self.assertTrue(public_save["saved"])
        self.assertEqual(public_save["url"], "/api/history/frame-1/public-image")
        self.assertEqual(Path(public_save["path"]).name, "frame-1_public.png")
        stored = json.loads((self.history_dir / "frame-1.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["status"], "completed")
        self.assertEqual(stored["custom_field"], {"keep": True})
        self.assertTrue(stored["public_save"]["saved"])
        self.assertFalse(stored["watermark"]["applied"])

    def test_list_history_skips_corrupted_item_with_warning(self) -> None:
        self.write_raw_history("valid", {"id": "valid", "created_at": "2026-06-18T09:00:00", "status": "queued"})
        (self.history_dir / "broken.json").write_text("{", encoding="utf-8")

        items, warnings = history_store.list_all_history_with_warnings()

        self.assertEqual([item["id"] for item in items], ["valid"])
        self.assertEqual(warnings, ["Skipped broken history entry: broken.json"])

    def test_history_item_store_validator_blocks_invalid_update(self) -> None:
        path = self.write_raw_history("valid", {"id": "valid", "created_at": "2026-06-18T09:00:00", "status": "queued"})
        original_text = path.read_text(encoding="utf-8")
        store = history_store._history_item_store("valid")

        with self.assertRaises(JsonStoreReadError):
            store.update(lambda _current: ["not", "a", "history", "item"], strict=True)

        self.assertEqual(path.read_text(encoding="utf-8"), original_text)


if __name__ == "__main__":
    unittest.main()
