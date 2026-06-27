from __future__ import annotations

from io import BytesIO
from pathlib import Path
import json
import tempfile
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from PIL import Image, ImageChops

from app import history_store, main, public_save_finish, public_save_jobs, settings_store, signature_store


class PublicSaveFinishSignatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.history_dir = self.root / "history"
        self.public_dir = self.root / "public"
        self.signature_dir = self.root / "signatures"
        self.signature_thumb_dir = self.signature_dir / "thumbs"
        for path in (self.history_dir, self.public_dir, self.signature_dir, self.signature_thumb_dir):
            path.mkdir(parents=True, exist_ok=True)

        self._original_history_dir = history_store.HISTORY_DIR
        self._original_public_dir = history_store.PUBLIC_DIR
        self._original_signature_dir = signature_store.SIGNATURE_DIR
        self._original_signature_thumb_dir = signature_store.THUMB_DIR
        self._original_signature_manifest_path = signature_store.MANIFEST_PATH
        history_store.HISTORY_DIR = self.history_dir
        history_store.PUBLIC_DIR = self.public_dir
        signature_store.SIGNATURE_DIR = self.signature_dir
        signature_store.THUMB_DIR = self.signature_thumb_dir
        signature_store.MANIFEST_PATH = self.signature_dir / "signatures.json"
        history_store._reset_history_cache_for_tests()
        public_save_jobs._reset_public_save_jobs_for_tests()
        self.session = "public-save-finish-test-session"
        main.SESSIONS.add(self.session)
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.SESSIONS.discard(self.session)
        history_store.HISTORY_DIR = self._original_history_dir
        history_store.PUBLIC_DIR = self._original_public_dir
        signature_store.SIGNATURE_DIR = self._original_signature_dir
        signature_store.THUMB_DIR = self._original_signature_thumb_dir
        signature_store.MANIFEST_PATH = self._original_signature_manifest_path
        history_store._reset_history_cache_for_tests()
        public_save_jobs._reset_public_save_jobs_for_tests()
        self._tmp.cleanup()

    def cookies(self) -> dict[str, str]:
        return {"anima_claude_session": self.session}

    def wait_public_save(self, history_id: str, job_id: str) -> dict:
        for _ in range(80):
            response = self.client.get(
                f"/api/history/{history_id}/public-save/status",
                params={"job_id": job_id},
                cookies=self.cookies(),
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            if data.get("status") in {"done", "failed"}:
                return data
            time.sleep(0.05)
        return data

    def _source(self, name: str = "source.png", color: tuple[int, int, int] = (40, 50, 60)) -> Path:
        source = self.root / name
        Image.new("RGB", (180, 120), color).save(source)
        return source

    def _signature_upload(self) -> dict:
        signature = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
        for x in range(10, 110):
            for y in range(15, 25):
                signature.putpixel((x, y), (0, 0, 0, 255))
        raw = BytesIO()
        signature.save(raw, "PNG")
        return signature_store.save_signature_upload("luna-signature.png", raw.getvalue())

    def test_signature_image_watermark_is_composited_without_path_leak(self) -> None:
        source = self._source()
        signature = self._signature_upload()
        item = {"id": "frame-sign", "image_path": str(source)}

        public_save = history_store.copy_public_image(
            item,
            {
                "enabled": True,
                "mode": "signature_image",
                "signature_image_id": signature["signature_id"],
                "signature_scale": 0.4,
                "opacity": 1,
                "position": "bottom_center",
                "margin": 6,
            },
        )

        output = Path(public_save["path"])
        self.assertEqual(output.name, "frame-sign_wm.png")
        self.assertTrue(item["watermark"]["applied"])
        self.assertEqual(item["watermark"]["mode"], "signature_image")
        self.assertEqual(public_save["signature_image_id"], signature["signature_id"])
        with Image.open(source).convert("RGB") as original, Image.open(output).convert("RGB") as watermarked:
            self.assertIsNotNone(ImageChops.difference(original, watermarked).getbbox())
        encoded = json.dumps(signature, ensure_ascii=False)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn('"path"', encoded)

    def test_signature_upload_endpoint_returns_safe_urls(self) -> None:
        signature = Image.new("RGBA", (48, 24), (0, 0, 0, 0))
        for x in range(8, 40):
            signature.putpixel((x, 12), (0, 0, 0, 255))
        raw = BytesIO()
        signature.save(raw, "PNG")

        response = self.client.post(
            "/api/signatures/upload",
            files={"file": ("signature.png", raw.getvalue(), "image/png")},
            cookies=self.cookies(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        item = body["item"]
        self.assertTrue(item["image_url"].startswith("/api/signatures/"))
        self.assertIn("?v=", item["image_url"])
        self.assertIn("?v=", item["thumbnail_url"])
        self.assertNotIn(str(self.root), json.dumps(body, ensure_ascii=False))
        image_response = self.client.get(item["image_url"], cookies=self.cookies())
        self.assertEqual(image_response.status_code, 200)
        self.assertNotIn("immutable", image_response.headers.get("cache-control", ""))
        self.assertIn("no-store", image_response.headers.get("cache-control", ""))
        thumb_response = self.client.get(item["thumbnail_url"], cookies=self.cookies())
        self.assertEqual(thumb_response.status_code, 200)
        self.assertNotIn("immutable", thumb_response.headers.get("cache-control", ""))

    def test_finish_preset_applies_when_explicitly_configured(self) -> None:
        source = self._source(color=(80, 80, 80))
        preset = self.root / "krita_itsumono.json"
        preset.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "preset": "krita_itsumono",
                    "operations": [{"type": "brightness_contrast", "brightness": 0.25, "contrast": 1.0}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        item = {"id": "frame-finish", "image_path": str(source)}

        with mock.patch.dict("os.environ", {"LUNA_PUBLIC_SAVE_FINISH_PRESET": str(preset)}, clear=False):
            public_save = history_store.copy_public_image(item, {"enabled": False}, {"finish_enabled": True, "finish_preset": "krita_itsumono"})

        output = Path(public_save["path"])
        self.assertEqual(output.name, "frame-finish_wm.png")
        self.assertTrue(public_save["finish_applied"])
        self.assertTrue(item["public_save_finish"]["applied"])
        with Image.open(source).convert("RGB") as original, Image.open(output).convert("RGB") as finished:
            self.assertIsNotNone(ImageChops.difference(original, finished).getbbox())

    def test_finish_preset_applies_krita_perchannel_curves(self) -> None:
        source = self._source(color=(100, 120, 130))
        preset = self.root / "krita_itsumono.json"
        preset.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "preset": "krita_itsumono",
                    "operations": [
                        {
                            "type": "krita_perchannel",
                            "n_transfers": 8,
                            "curves": {
                                "curve0": "0,0;1,1;",
                                "curve1": "0,0;1,0;",
                                "curve2": "0,0;1,1;",
                                "curve3": "0,1;1,1;",
                                "curve4": "0,0;1,1;",
                                "curve5": "0,0;1,1;",
                                "curve6": "0,0;1,1;",
                                "curve7": "0,0;1,1;",
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        item = {"id": "frame-krita-curves", "image_path": str(source)}

        with mock.patch.dict("os.environ", {"LUNA_PUBLIC_SAVE_FINISH_PRESET": str(preset)}, clear=False):
            public_save = history_store.copy_public_image(
                item,
                {"enabled": False},
                {"finish_enabled": True, "finish_preset": "krita_itsumono"},
            )

        self.assertTrue(public_save["finish_applied"])
        self.assertEqual(item["public_save_finish"]["effective_operation_count"], 1)
        with Image.open(public_save["path"]).convert("RGB") as finished:
            red, green, blue = finished.getpixel((10, 10))
        self.assertLessEqual(red, 1)
        self.assertEqual(green, 120)
        self.assertGreaterEqual(blue, 254)

    def test_finish_preset_applies_krita_perchannel_255_curves(self) -> None:
        source = self._source(color=(100, 120, 130))
        preset = self.root / "krita_itsumono.json"
        preset.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "preset": "krita_itsumono",
                    "operations": [
                        {
                            "type": "krita_perchannel",
                            "curves": {
                                "curve0": "0,0;255,255;",
                                "curve1": "0,0;64,55;191,201;255,255;",
                                "curve2": "0,0;255,255;",
                                "curve3": "0,0;64,74;191,181;255,255;",
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        item = {"id": "frame-krita-255-curves", "image_path": str(source)}

        with mock.patch.dict("os.environ", {"LUNA_PUBLIC_SAVE_FINISH_PRESET": str(preset)}, clear=False):
            public_save = history_store.copy_public_image(
                item,
                {"enabled": False},
                {"finish_enabled": True, "finish_preset": "krita_itsumono"},
            )

        self.assertTrue(public_save["finish_applied"])
        self.assertEqual(public_save["finish_effective_operation_count"], 1)
        with Image.open(source).convert("RGB") as original, Image.open(public_save["path"]).convert("RGB") as finished:
            self.assertIsNotNone(ImageChops.difference(original, finished).getbbox())

    def test_finish_color_operation_is_not_filtered_as_identity(self) -> None:
        source = self._source(color=(100, 40, 180))
        preset = self.root / "krita_itsumono.json"
        preset.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "preset": "krita_itsumono",
                    "operations": [{"type": "saturation", "factor": 0.0}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        item = {"id": "frame-color-finish", "image_path": str(source)}

        with mock.patch.dict("os.environ", {"LUNA_PUBLIC_SAVE_FINISH_PRESET": str(preset)}, clear=False):
            public_save = history_store.copy_public_image(
                item,
                {"enabled": False},
                {"finish_enabled": True, "finish_preset": "krita_itsumono"},
            )

        self.assertTrue(public_save["finish_applied"])
        self.assertEqual(public_save["finish_effective_operation_count"], 1)
        self.assertEqual(item["public_save_finish"]["changed_operation_count"], 1)
        with Image.open(source).convert("RGB") as original, Image.open(public_save["path"]).convert("RGB") as finished:
            self.assertIsNotNone(ImageChops.difference(original, finished).getbbox())

    def test_missing_finish_preset_is_noop_for_jpeg_source(self) -> None:
        source = self._source("source.jpg", color=(120, 100, 80))
        item = {"id": "frame-jpeg-noop", "image_path": str(source)}

        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(
            public_save_finish,
            "_candidate_paths",
            return_value=[self.root / "missing_krita_itsumono.json"],
        ):
            public_save = history_store.copy_public_image(
                item,
                {"enabled": False},
                {"finish_enabled": True, "finish_preset": "krita_itsumono"},
            )

        output = Path(public_save["path"])
        self.assertEqual(output.name, "frame-jpeg-noop_public.jpg")
        self.assertTrue(output.exists())
        self.assertFalse(public_save["finish_applied"])
        self.assertFalse(item["public_save_finish"]["applied"])

    def test_public_save_endpoint_uses_saved_finish_settings_when_request_omits_finish_fields(self) -> None:
        source = self._source(color=(90, 90, 90))
        preset = self.root / "krita_itsumono.json"
        preset.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "preset": "krita_itsumono",
                    "operations": [{"type": "brightness_contrast", "brightness": 0.2}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        history_store.save_history_item({"id": "frame-api-finish-default", "image_path": str(source)})
        app_settings = {
            "public_save": {
                "finish_enabled": True,
                "finish_preset": "krita_itsumono",
                "apply_watermark": False,
            },
            "watermark": {"enabled": False},
        }

        with mock.patch.object(public_save_finish, "_candidate_paths", return_value=[preset]), mock.patch(
            "app.api.history.load_app_settings",
            return_value=app_settings,
        ):
            response = self.client.post(
                "/api/history/frame-api-finish-default/public-save",
                json={"apply_watermark": False},
                cookies=self.cookies(),
            )

        self.assertEqual(response.status_code, 200)
        public_save = response.json()["public_save"]
        self.assertTrue(public_save["finish_applied"])
        self.assertTrue(public_save["finish_enabled"])
        self.assertEqual(public_save["finish_preset"], "krita_itsumono")

    def test_public_save_async_applies_saved_finish_settings(self) -> None:
        source = self._source(color=(90, 90, 90))
        preset = self.root / "krita_itsumono.json"
        preset.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "preset": "krita_itsumono",
                    "operations": [{"type": "brightness_contrast", "brightness": 0.2}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        history_store.save_history_item({"id": "frame-api-finish-async", "image_path": str(source)})
        app_settings = {
            "public_save": {
                "finish_enabled": True,
                "finish_preset": "krita_itsumono",
                "apply_watermark": False,
            },
            "watermark": {"enabled": False},
        }

        with mock.patch.object(public_save_finish, "_candidate_paths", return_value=[preset]), mock.patch(
            "app.api.history.load_app_settings",
            return_value=app_settings,
        ):
            response = self.client.post(
                "/api/history/frame-api-finish-async/public-save",
                json={"apply_watermark": False, "async_save": True},
                cookies=self.cookies(),
            )
            self.assertEqual(response.status_code, 200)
            done = self.wait_public_save("frame-api-finish-async", response.json()["job_id"])

        self.assertEqual(done["status"], "done")
        public_save = done["public_save"]
        self.assertTrue(public_save["finish_applied"])
        self.assertTrue(public_save["finish_enabled"])
        self.assertEqual(public_save["finish_effective_operation_count"], 1)

    def test_public_save_endpoint_can_explicitly_disable_saved_finish_settings(self) -> None:
        source = self._source(color=(90, 90, 90))
        preset = self.root / "krita_itsumono.json"
        preset.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "preset": "krita_itsumono",
                    "operations": [{"type": "brightness_contrast", "brightness": 0.2}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        history_store.save_history_item({"id": "frame-api-finish-off", "image_path": str(source)})
        app_settings = {
            "public_save": {
                "finish_enabled": True,
                "finish_preset": "krita_itsumono",
                "apply_watermark": False,
            },
            "watermark": {"enabled": False},
        }

        with mock.patch.object(public_save_finish, "_candidate_paths", return_value=[preset]), mock.patch(
            "app.api.history.load_app_settings",
            return_value=app_settings,
        ):
            response = self.client.post(
                "/api/history/frame-api-finish-off/public-save",
                json={"apply_watermark": False, "finish_enabled": False},
                cookies=self.cookies(),
            )

        self.assertEqual(response.status_code, 200)
        public_save = response.json()["public_save"]
        self.assertFalse(public_save["finish_applied"])
        self.assertFalse(public_save["finish_enabled"])
        self.assertEqual(Path(public_save["path"]).name, "frame-api-finish-off_public.png")

    def test_text_watermark_saves_jpeg_source(self) -> None:
        source = self._source("source.jpg", color=(20, 30, 40))
        item = {"id": "frame-jpeg-watermark", "image_path": str(source)}

        public_save = history_store.copy_public_image(
            item,
            {"enabled": True, "text": "TEST", "opacity": 0.8, "size": 24, "position": "bottom_right"},
        )

        output = Path(public_save["path"])
        self.assertEqual(output.name, "frame-jpeg-watermark_wm.jpg")
        self.assertTrue(output.exists())
        with Image.open(output) as image:
            self.assertEqual(image.mode, "RGB")

    def test_finish_example_is_not_treated_as_operational_preset(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(
            public_save_finish,
            "_candidate_paths",
            return_value=[public_save_finish.ROOT_DIR / "config" / "krita_itsumono.example.json"],
        ):
            status = public_save_finish.public_save_finish_status(
                {"public_save": {"finish_enabled": True, "finish_preset": "krita_itsumono"}}
            )

        self.assertTrue(status["enabled"])
        self.assertFalse(status["available"])
        self.assertIn("example preset only", " ".join(status["warnings"]))

    def test_settings_sanitize_preserves_signature_and_finish_settings(self) -> None:
        settings = settings_store.sanitize_app_settings(
            {
                "watermark": {
                    "enabled": True,
                    "mode": "signature_image",
                    "position": "bottom_center",
                    "signature_image_id": "sig_test",
                    "signature_scale": "2",
                    "opacity": "bad",
                },
                "public_save": {
                    "apply_watermark": True,
                    "finish_enabled": True,
                    "finish_preset": "krita_itsumono",
                },
            }
        )

        self.assertEqual(settings["watermark"]["mode"], "signature_image")
        self.assertEqual(settings["watermark"]["position"], "bottom_center")
        self.assertEqual(settings["watermark"]["signature_image_id"], "sig_test")
        self.assertEqual(settings["watermark"]["signature_scale"], 0.6)
        self.assertEqual(settings["watermark"]["opacity"], settings_store.DEFAULT_APP_SETTINGS["watermark"]["opacity"])
        self.assertTrue(settings["public_save"]["finish_enabled"])
        self.assertEqual(settings["public_save"]["finish_preset"], "krita_itsumono")


if __name__ == "__main__":
    unittest.main()
