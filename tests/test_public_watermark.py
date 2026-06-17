from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageChops

from app import history_store


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


if __name__ == "__main__":
    unittest.main()
