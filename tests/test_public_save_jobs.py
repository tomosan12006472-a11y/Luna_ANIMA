from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from PIL import Image

from app import history_store, main, public_save_jobs


class PublicSaveJobsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.history_dir = self.root / "history"
        self.public_dir = self.root / "public"
        self.image_dir = self.root / "images"
        self.thumbnail_dir = self.root / "thumbnails"
        for path in (self.history_dir, self.public_dir, self.image_dir, self.thumbnail_dir):
            path.mkdir(parents=True, exist_ok=True)

        self._original_history_dir = history_store.HISTORY_DIR
        self._original_public_dir = history_store.PUBLIC_DIR
        self._original_image_dir = history_store.IMAGE_DIR
        self._original_thumbnail_dir = history_store.THUMBNAIL_DIR
        history_store.HISTORY_DIR = self.history_dir
        history_store.PUBLIC_DIR = self.public_dir
        history_store.IMAGE_DIR = self.image_dir
        history_store.THUMBNAIL_DIR = self.thumbnail_dir
        history_store._reset_history_cache_for_tests()
        public_save_jobs._reset_public_save_jobs_for_tests()
        self._settings_patch = mock.patch(
            "app.api.history.load_app_settings",
            return_value={
                "public_save": {
                    "apply_watermark": False,
                    "finish_enabled": False,
                    "finish_preset": "krita_itsumono",
                },
                "watermark": {"enabled": False},
            },
        )
        self._settings_patch.start()

        self.session = "public-save-test-session"
        main.SESSIONS.add(self.session)
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.SESSIONS.discard(self.session)
        history_store.HISTORY_DIR = self._original_history_dir
        history_store.PUBLIC_DIR = self._original_public_dir
        history_store.IMAGE_DIR = self._original_image_dir
        history_store.THUMBNAIL_DIR = self._original_thumbnail_dir
        self._settings_patch.stop()
        history_store._reset_history_cache_for_tests()
        public_save_jobs._reset_public_save_jobs_for_tests()
        self._tmp.cleanup()

    def cookies(self) -> dict[str, str]:
        return {"anima_claude_session": self.session}

    def write_history(self, history_id: str = "frame-1") -> Path:
        source = self.root / f"{history_id}.png"
        Image.new("RGB", (64, 48), (20, 30, 40)).save(source)
        history_store.save_history_item(
            {
                "id": history_id,
                "created_at": "2026-06-25T10:00:00",
                "status": "completed",
                "image_path": str(source),
                "thumbnail_path": str(source),
                "public_save": {"saved": False},
                "watermark": {"applied": False},
            }
        )
        return source

    def wait_public_save(self, history_id: str, job_id: str, timeout: float = 3.0) -> dict:
        deadline = time.time() + timeout
        latest = {}
        while time.time() < deadline:
            response = self.client.get(
                f"/api/history/{history_id}/public-save/status",
                params={"job_id": job_id},
                cookies=self.cookies(),
            )
            self.assertEqual(response.status_code, 200)
            latest = response.json()
            if latest.get("status") in {"done", "failed"}:
                return latest
            time.sleep(0.05)
        return latest

    def assert_no_async_path_leak(self, body: dict) -> None:
        encoded = json.dumps(body, ensure_ascii=False)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn('"path"', encoded)
        self.assertNotIn('"image_path"', encoded)
        self.assertNotIn('"thumbnail_path"', encoded)

    def test_existing_synchronous_public_save_still_works(self) -> None:
        self.write_history("frame-sync")

        response = self.client.post(
            "/api/history/frame-sync/public-save",
            json={"apply_watermark": False, "watermark_client": "current"},
            cookies=self.cookies(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["public_save"]["saved"])
        self.assertFalse(body["public_save"]["cached"])
        self.assertTrue((self.public_dir / "frame-sync_public.png").exists())

    def test_async_public_save_returns_queued_then_done(self) -> None:
        self.write_history("frame-async")

        response = self.client.post(
            "/api/history/frame-async/public-save",
            json={"apply_watermark": False, "watermark_client": "current", "async_save": True},
            cookies=self.cookies(),
        )
        body = response.json()
        done = self.wait_public_save("frame-async", body["job_id"])

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["queued"])
        self.assertEqual(done["status"], "done")
        self.assertTrue(done["public_save"]["saved"])
        self.assertTrue(done["public_image_url"].startswith("/api/history/frame-async/public-image?v="))
        self.assert_no_async_path_leak(done)
        current = json.loads((self.history_dir / "frame-async.json").read_text(encoding="utf-8"))
        self.assertTrue(current["public_save"]["saved"])

    def test_async_public_save_failure_marks_job_failed(self) -> None:
        self.write_history("frame-fail")
        secret = r"SECRET_SENTINEL D:\secret\copy boom"

        with mock.patch.object(public_save_jobs, "copy_public_image", side_effect=RuntimeError(secret)):
            response = self.client.post(
                "/api/history/frame-fail/public-save",
                json={"apply_watermark": False, "watermark_client": "current", "async_save": True},
                cookies=self.cookies(),
            )
            body = response.json()
            failed = self.wait_public_save("frame-fail", body["job_id"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"], "public save failed")
        self.assertNotIn("SECRET_SENTINEL", json.dumps(failed))
        self.assertNotIn(r"D:\secret", json.dumps(failed))

    def test_async_public_save_reuses_cached_result(self) -> None:
        self.write_history("frame-cache")
        first = self.client.post(
            "/api/history/frame-cache/public-save",
            json={"apply_watermark": False, "watermark_client": "current"},
            cookies=self.cookies(),
        )
        self.assertEqual(first.status_code, 200)

        response = self.client.post(
            "/api/history/frame-cache/public-save",
            json={"apply_watermark": False, "watermark_client": "current", "async_save": True},
            cookies=self.cookies(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "done")
        self.assertFalse(body["queued"])
        self.assertTrue(body["public_save"]["cached"])
        self.assert_no_async_path_leak(body)

    def test_public_save_status_rejects_job_id_for_other_history(self) -> None:
        self.write_history("frame-a")
        self.write_history("frame-b")
        response = self.client.post(
            "/api/history/frame-a/public-save",
            json={"apply_watermark": False, "watermark_client": "current", "async_save": True},
            cookies=self.cookies(),
        )
        self.assertEqual(response.status_code, 200)
        job_id = response.json()["job_id"]

        mismatch = self.client.get(
            "/api/history/frame-b/public-save/status",
            params={"job_id": job_id},
            cookies=self.cookies(),
        )

        self.assertEqual(mismatch.status_code, 404)
        self.wait_public_save("frame-a", job_id)

    def test_public_save_status_rejects_missing_explicit_job_id(self) -> None:
        self.write_history("frame-missing")

        response = self.client.get(
            "/api/history/frame-missing/public-save/status",
            params={"job_id": "public-save-missing"},
            cookies=self.cookies(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "public save job not found")

    def test_public_save_status_recovers_done_when_job_registry_is_missing(self) -> None:
        self.write_history("frame-recover")
        saved = self.client.post(
            "/api/history/frame-recover/public-save",
            json={"apply_watermark": False, "watermark_client": "current"},
            cookies=self.cookies(),
        )
        self.assertEqual(saved.status_code, 200)

        response = self.client.get(
            "/api/history/frame-recover/public-save/status",
            params={"job_id": "public-save-missing"},
            cookies=self.cookies(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "done")
        self.assertTrue(body["public_image_url"].startswith("/api/history/frame-recover/public-image?v="))
        self.assert_no_async_path_leak(body)

    def test_public_image_serves_saved_file_when_public_save_path_is_missing(self) -> None:
        self.write_history("frame-pathless")
        output = self.public_dir / "frame-pathless_public.png"
        Image.new("RGB", (32, 24), (90, 20, 10)).save(output)
        item = history_store.load_history_item("frame-pathless")
        self.assertIsNotNone(item)
        assert item is not None
        item["public_save"] = {
            "saved": True,
            "url": "/api/history/frame-pathless/public-image",
            "filename": output.name,
        }
        item["public_image_url"] = "/api/history/frame-pathless/public-image"
        history_store.save_history_item(item)

        response = self.client.get(
            "/api/history/frame-pathless/public-image",
            cookies=self.cookies(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content[:8], b"\x89PNG\r\n\x1a\n")

    def test_public_image_endpoint_is_not_immutable_cached(self) -> None:
        self.write_history("frame-public-cache")
        saved = self.client.post(
            "/api/history/frame-public-cache/public-save",
            json={"apply_watermark": False, "watermark_client": "current"},
            cookies=self.cookies(),
        )
        self.assertEqual(saved.status_code, 200)

        response = self.client.get(
            "/api/history/frame-public-cache/public-image",
            cookies=self.cookies(),
        )

        self.assertEqual(response.status_code, 200)
        cache_control = response.headers.get("cache-control", "")
        self.assertIn("no-store", cache_control)
        self.assertNotIn("immutable", cache_control)

    def test_public_image_does_not_serve_conventional_file_when_not_saved(self) -> None:
        self.write_history("frame-not-saved")
        output = self.public_dir / "frame-not-saved_public.png"
        Image.new("RGB", (32, 24), (120, 40, 20)).save(output)

        response = self.client.get(
            "/api/history/frame-not-saved/public-image",
            cookies=self.cookies(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "public image not found")

    def test_async_public_save_reuses_saved_public_image_when_source_is_missing(self) -> None:
        source = self.write_history("frame-source-missing")
        output = self.public_dir / "frame-source-missing_public.png"
        Image.new("RGB", (32, 24), (10, 80, 40)).save(output)
        item = history_store.load_history_item("frame-source-missing")
        self.assertIsNotNone(item)
        assert item is not None
        item["public_save"] = {
            "saved": True,
            "url": "/api/history/frame-source-missing/public-image",
            "filename": output.name,
        }
        item["public_image_url"] = "/api/history/frame-source-missing/public-image"
        history_store.save_history_item(item)
        source.unlink()

        response = self.client.post(
            "/api/history/frame-source-missing/public-save",
            json={"apply_watermark": False, "watermark_client": "current", "async_save": True},
            cookies=self.cookies(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "done")
        self.assertEqual(body["public_image_url"], "/api/history/frame-source-missing/public-image")
        self.assert_no_async_path_leak(body)

    def test_async_public_save_conflicts_when_settings_differ_from_active_job(self) -> None:
        self.write_history("frame-conflict")

        def slow_copy(item: dict, watermark: dict, finish: dict | None = None) -> dict:
            time.sleep(0.5)
            return history_store.copy_public_image(item, watermark, finish)

        with mock.patch.object(public_save_jobs, "copy_public_image", side_effect=slow_copy):
            first = self.client.post(
                "/api/history/frame-conflict/public-save",
                json={"apply_watermark": False, "watermark_client": "current", "async_save": True},
                cookies=self.cookies(),
            )
            second = self.client.post(
                "/api/history/frame-conflict/public-save",
                json={
                    "apply_watermark": True,
                    "watermark_client": "current",
                    "watermark": {"text": "DIFFERENT", "position": "bottom_right", "opacity": 0.8, "size": 20},
                    "async_save": True,
                },
                cookies=self.cookies(),
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertIn("different settings", second.json()["detail"])
        self.wait_public_save("frame-conflict", first.json()["job_id"])


if __name__ == "__main__":
    unittest.main()
