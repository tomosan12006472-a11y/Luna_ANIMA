from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app import _shared_utils, i2i_store, reference_store, settings_store
from app.storage.json_store import JsonStore, JsonStoreReadError


class JsonStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_read_non_strict_returns_default_for_broken_json(self) -> None:
        path = self.root / "payload.json"
        path.write_text("{", encoding="utf-8")
        store = JsonStore(path, default_factory=lambda: {"items": []}, label="payload")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            self.assertEqual(store.read(strict=False), {"items": []})

    def test_read_strict_raises_for_broken_json(self) -> None:
        path = self.root / "payload.json"
        path.write_text("{", encoding="utf-8")
        store = JsonStore(path, default_factory=dict, label="payload")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                store.read(strict=True)

    def test_write_uses_atomic_json_output(self) -> None:
        path = self.root / "nested" / "payload.json"
        store = JsonStore(path, default_factory=dict, label="payload")

        store.write({"message": "こんにちは", "items": [1, 2]})

        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"message": "こんにちは", "items": [1, 2]})
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_update_strict_reads_then_writes(self) -> None:
        path = self.root / "payload.json"
        path.write_text(json.dumps({"count": 1}), encoding="utf-8")
        store = JsonStore(path, default_factory=dict, label="payload")

        result = store.update(lambda data: {**data, "count": data["count"] + 1})

        self.assertEqual(result, {"count": 2})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"count": 2})

    def test_update_does_not_overwrite_unreadable_json(self) -> None:
        path = self.root / "payload.json"
        path.write_text("{", encoding="utf-8")
        store = JsonStore(path, default_factory=lambda: {"count": 0}, label="payload")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                store.update(lambda data: {"count": data["count"] + 1})

        self.assertEqual(path.read_text(encoding="utf-8"), "{")


class StoreMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

        self._settings_path = settings_store.SETTINGS_PATH
        self.settings_path = self.root / "settings.json"
        settings_store.SETTINGS_PATH = self.settings_path

        self._reference_manifest_path = reference_store.MANIFEST_PATH
        self._reference_dir = reference_store.REFERENCE_DIR
        self._reference_thumb_dir = reference_store.THUMB_DIR
        self.reference_dir = self.root / "reference_inputs"
        self.reference_thumb_dir = self.reference_dir / "thumbs"
        reference_store.MANIFEST_PATH = self.reference_dir / "reference_inputs.json"
        reference_store.REFERENCE_DIR = self.reference_dir
        reference_store.THUMB_DIR = self.reference_thumb_dir
        self.reference_thumb_dir.mkdir(parents=True, exist_ok=True)

        self._i2i_manifest_path = i2i_store.MANIFEST_PATH
        self._i2i_dir = i2i_store.I2I_DIR
        self._i2i_thumb_dir = i2i_store.THUMB_DIR
        self._i2i_prepared_dir = i2i_store.PREPARED_DIR
        self.i2i_dir = self.root / "i2i_inputs"
        self.i2i_thumb_dir = self.i2i_dir / "thumbs"
        self.i2i_prepared_dir = self.i2i_dir / "prepared"
        i2i_store.MANIFEST_PATH = self.i2i_dir / "i2i_inputs.json"
        i2i_store.I2I_DIR = self.i2i_dir
        i2i_store.THUMB_DIR = self.i2i_thumb_dir
        i2i_store.PREPARED_DIR = self.i2i_prepared_dir
        self.i2i_thumb_dir.mkdir(parents=True, exist_ok=True)
        self.i2i_prepared_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        settings_store.SETTINGS_PATH = self._settings_path
        reference_store.MANIFEST_PATH = self._reference_manifest_path
        reference_store.REFERENCE_DIR = self._reference_dir
        reference_store.THUMB_DIR = self._reference_thumb_dir
        i2i_store.MANIFEST_PATH = self._i2i_manifest_path
        i2i_store.I2I_DIR = self._i2i_dir
        i2i_store.THUMB_DIR = self._i2i_thumb_dir
        i2i_store.PREPARED_DIR = self._i2i_prepared_dir
        self._tmp.cleanup()

    def image_bytes(self) -> bytes:
        from io import BytesIO

        from PIL import Image

        output = BytesIO()
        Image.new("RGB", (32, 24), (20, 40, 80)).save(output, "PNG")
        return output.getvalue()

    def test_settings_store_load_save_reset_preserves_structure(self) -> None:
        default_settings = settings_store.load_app_settings()
        self.assertEqual(default_settings["workflow_mode"], "anima")
        self.assertIn("image_to_image", default_settings)

        saved = settings_store.save_app_settings({"width": 768, "image_to_image": {"enabled": True, "denoise": 0.33}})
        loaded = settings_store.load_app_settings()
        self.assertEqual(saved["width"], 768)
        self.assertEqual(loaded["width"], 768)
        self.assertEqual(loaded["image_to_image"]["denoise"], 0.33)
        self.assertIn("prompt_converter", json.loads(self.settings_path.read_text(encoding="utf-8")))

        reset = settings_store.reset_app_settings()
        self.assertEqual(reset["width"], settings_store.DEFAULT_APP_SETTINGS["width"])
        self.assertEqual(settings_store.load_app_settings()["width"], settings_store.DEFAULT_APP_SETTINGS["width"])

    def test_reference_store_list_get_save_delete_with_json_store_manifest(self) -> None:
        item = reference_store.save_reference_upload("sample.png", self.image_bytes(), app_scope="anima", module="outfit")

        self.assertEqual(item["module"], "outfit")
        self.assertTrue(item["image_url"].startswith("/api/reference/images/"))
        self.assertEqual(reference_store.get_reference_image(item["image_id"])["image_id"], item["image_id"])
        self.assertEqual([entry["image_id"] for entry in reference_store.list_reference_images(module="outfit")], [item["image_id"]])
        manifest = json.loads(reference_store.MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertIn(item["image_id"], manifest["items"])

        self.assertTrue(reference_store.delete_reference_image(item["image_id"]))
        self.assertIsNone(reference_store.get_reference_image(item["image_id"]))
        self.assertFalse(Path(item["path"]).exists())
        self.assertFalse(Path(item["thumbnail_path"]).exists())

    def test_i2i_store_list_get_save_delete_with_json_store_manifest(self) -> None:
        item = i2i_store.save_i2i_upload("sample.png", self.image_bytes(), app_scope="anima")

        self.assertTrue(item["image_url"].startswith("/api/i2i/images/"))
        self.assertEqual(i2i_store.get_i2i_image(item["image_id"])["image_id"], item["image_id"])
        self.assertEqual([entry["image_id"] for entry in i2i_store.list_i2i_images()], [item["image_id"]])
        manifest = json.loads(i2i_store.MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertIn(item["image_id"], manifest["items"])

        self.assertTrue(i2i_store.delete_i2i_image(item["image_id"]))
        self.assertIsNone(i2i_store.get_i2i_image(item["image_id"]))
        self.assertFalse(Path(item["path"]).exists())
        self.assertFalse(Path(item["thumbnail_path"]).exists())


if __name__ == "__main__":
    unittest.main()
