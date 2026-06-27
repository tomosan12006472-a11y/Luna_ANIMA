from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageChops

from app import history_store
from app import main
from app._shared_utils import JsonStoreReadError


class PublicWatermarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.history_dir = self.root / "history"
        self.public_dir = self.root / "public"
        self.history_dir.mkdir()
        self.public_dir.mkdir()
        self._original_history_dir = history_store.HISTORY_DIR
        self._original_public_dir = history_store.PUBLIC_DIR
        history_store.HISTORY_DIR = self.history_dir
        history_store.PUBLIC_DIR = self.public_dir
        history_store._reset_history_cache_for_tests()

    def tearDown(self) -> None:
        history_store.HISTORY_DIR = self._original_history_dir
        history_store.PUBLIC_DIR = self._original_public_dir
        history_store._reset_history_cache_for_tests()
        self._tmp.cleanup()

    def test_public_save_applies_watermark_when_enabled(self) -> None:
        source = self.root / "source.png"
        Image.new("RGB", (320, 180), (20, 30, 40)).save(source)
        item = {"id": "frame-1", "image_path": str(source)}

        public_save = history_store.copy_public_image(
            item,
            {"enabled": True, "text": "TEST", "opacity": 0.8, "size": 28, "position": "bottom_right"},
        )

        output = Path(public_save["path"])
        self.assertEqual(output.name, "frame-1_wm.png")
        self.assertTrue(output.exists())
        self.assertTrue(item["watermark"]["applied"])
        with Image.open(source).convert("RGB") as original, Image.open(output).convert("RGB") as watermarked:
            self.assertIsNotNone(ImageChops.difference(original, watermarked).getbbox())

    def test_public_save_url_changes_when_settings_hash_changes(self) -> None:
        source = self.root / "source.png"
        Image.new("RGB", (320, 180), (20, 30, 40)).save(source)
        item = {"id": "frame-versioned", "image_path": str(source)}

        first = history_store.copy_public_image(
            item,
            {"enabled": True, "text": "OLD", "opacity": 0.8, "size": 28, "position": "bottom_right"},
        )
        second = history_store.copy_public_image(
            item,
            {"enabled": True, "text": "NEW", "opacity": 0.8, "size": 28, "position": "bottom_right"},
        )

        self.assertTrue(first["url"].startswith("/api/history/frame-versioned/public-image?v="))
        self.assertTrue(second["url"].startswith("/api/history/frame-versioned/public-image?v="))
        self.assertNotEqual(first["url"], second["url"])
        self.assertNotEqual(first["settings_hash"], second["settings_hash"])

    def test_public_save_preserves_newer_history_status(self) -> None:
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
            }
        )
        stale_item = history_store.load_history_item("frame-1")
        self.assertIsNotNone(stale_item)

        history_store.update_pending_history_status("frame-1", "stale", "Timed out waiting for ComfyUI history")
        public_save = history_store.copy_public_image(stale_item or {}, {"enabled": False})

        current = history_store.load_history_item("frame-1")
        self.assertIsNotNone(current)
        self.assertTrue(public_save["saved"])
        self.assertEqual(current["status"], "stale")
        self.assertEqual(current["queue"]["status"], "stale")
        self.assertEqual(current["queue"]["error"], "Timed out waiting for ComfyUI history")
        self.assertTrue(current["public_save"]["saved"])
        self.assertFalse(current["watermark"]["applied"])

    def test_public_save_stops_when_current_history_is_unreadable(self) -> None:
        source = self.root / "source.png"
        Image.new("RGB", (320, 180), (20, 30, 40)).save(source)
        history_path = self.history_dir / "frame-1.json"
        history_path.write_text("{", encoding="utf-8")
        original_text = history_path.read_text(encoding="utf-8")
        stale_item = {
            "id": "frame-1",
            "created_at": "2026-06-18T09:00:00",
            "status": "completed",
            "image_path": str(source),
            "thumbnail_path": str(source),
            "public_save": {"saved": False},
            "watermark": {"applied": False},
        }

        with self.assertRaises(JsonStoreReadError):
            history_store.copy_public_image(stale_item, {"enabled": False})

        self.assertEqual(history_path.read_text(encoding="utf-8"), original_text)

    def test_legacy_public_save_request_uses_saved_watermark_settings(self) -> None:
        watermark = main.resolve_public_save_watermark(
            main.PublicSaveRequest(apply_watermark=False, watermark={"enabled": False}),
            {
                "watermark": {"enabled": True, "text": "@Saved", "position": "top_left", "opacity": 0.5, "size": 24},
                "public_save": {"apply_watermark": True},
            },
        )
        self.assertTrue(watermark["enabled"])
        self.assertEqual(watermark["text"], "@Saved")

    def test_current_public_save_request_can_disable_watermark(self) -> None:
        watermark = main.resolve_public_save_watermark(
            main.PublicSaveRequest(apply_watermark=False, watermark={"enabled": False}, watermark_client="current"),
            {
                "watermark": {"enabled": True, "text": "@Saved"},
                "public_save": {"apply_watermark": True},
            },
        )
        self.assertFalse(watermark["enabled"])


if __name__ == "__main__":
    unittest.main()
