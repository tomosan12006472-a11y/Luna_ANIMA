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

        self.session = "public-save-test-session"
        main.SESSIONS.add(self.session)
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.SESSIONS.discard(self.session)
        history_store.HISTORY_DIR = self._original_history_dir
        history_store.PUBLIC_DIR = self._original_public_dir
        history_store.IMAGE_DIR = self._original_image_dir
        history_store.THUMBNAIL_DIR = self._original_thumbnail_dir
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
        self.assertEqual(done["public_image_url"], "/api/history/frame-async/public-image")
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

    def test_async_public_save_conflicts_when_settings_differ_from_active_job(self) -> None:
        self.write_history("frame-conflict")

        def slow_copy(item: dict, watermark: dict) -> dict:
            time.sleep(0.5)
            return history_store.copy_public_image(item, watermark)

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
