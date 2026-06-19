from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app import history_store
from app._shared_utils import JsonStoreReadError


class HistoryCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.history_dir = Path(self._tmp.name)
        self._original_history_dir = history_store.HISTORY_DIR
        history_store.HISTORY_DIR = self.history_dir
        history_store._reset_history_cache_for_tests()

    def tearDown(self) -> None:
        history_store.HISTORY_DIR = self._original_history_dir
        history_store._reset_history_cache_for_tests()
        self._tmp.cleanup()

    def write_item(self, history_id: str, created_at: str, **extra: object) -> Path:
        path = self.history_dir / f"{history_id}.json"
        payload = {"id": history_id, "created_at": created_at, "status": "queued", **extra}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def list_ids(self) -> list[str]:
        items, warnings = history_store.list_all_history_with_warnings()
        self.assertEqual(warnings, [])
        return [str(item.get("id")) for item in items]

    def list_items_by_id(self) -> dict[str, dict[str, object]]:
        items, warnings = history_store.list_all_history_with_warnings()
        self.assertEqual(warnings, [])
        return {str(item.get("id")): item for item in items}

    def test_second_call_uses_cache_without_rereading_files(self) -> None:
        self.write_item("older", "2026-06-10T10:00:00")
        self.write_item("newer", "2026-06-11T10:00:00")
        read_paths: list[str] = []
        original_read_text = Path.read_text

        def counted_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path.parent == self.history_dir and path.suffix == ".json":
                read_paths.append(path.name)
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", counted_read_text):
            self.assertEqual(self.list_ids(), ["newer", "older"])
            self.assertEqual(self.list_ids(), ["newer", "older"])
        self.assertEqual(sorted(read_paths), ["newer.json", "older.json"])

    def test_file_addition_refreshes_cache(self) -> None:
        self.write_item("first", "2026-06-10T10:00:00")
        self.assertEqual(self.list_ids(), ["first"])
        self.write_item("second", "2026-06-11T10:00:00")
        self.assertEqual(self.list_ids(), ["second", "first"])

    def test_file_update_refreshes_cache_when_mtime_changes(self) -> None:
        path = self.write_item("entry", "2026-06-10T10:00:00", status="queued")
        self.assertEqual(history_store.list_all_history_with_warnings()[0][0]["status"], "queued")
        self.write_item("entry", "2026-06-10T10:00:00", status="failed")
        stat = path.stat()
        next_time = stat.st_mtime_ns + 2_000_000_000
        Path(path).touch()
        import os

        os.utime(path, ns=(next_time, next_time))
        self.assertEqual(history_store.list_all_history_with_warnings()[0][0]["status"], "failed")

    def test_older_file_update_refreshes_cache_when_latest_mtime_and_total_size_are_unchanged(self) -> None:
        older = self.write_item("older", "2026-06-10T10:00:00", status="queued")
        newer = self.write_item("newer", "2026-06-11T10:00:00", status="queued")
        base_time = 1_800_000_000_000_000_000
        os.utime(older, ns=(base_time, base_time))
        os.utime(newer, ns=(base_time + 3_000_000_000, base_time + 3_000_000_000))
        self.assertEqual(self.list_items_by_id()["older"]["status"], "queued")

        self.write_item("older", "2026-06-10T10:00:00", status="failed")
        os.utime(older, ns=(base_time + 1_000_000_000, base_time + 1_000_000_000))

        self.assertEqual(self.list_items_by_id()["older"]["status"], "failed")

    def test_file_deletion_refreshes_cache(self) -> None:
        self.write_item("first", "2026-06-10T10:00:00")
        second = self.write_item("second", "2026-06-11T10:00:00")
        self.assertEqual(self.list_ids(), ["second", "first"])
        second.unlink()
        self.assertEqual(self.list_ids(), ["first"])

    def test_pending_status_update_raises_when_history_stays_unreadable(self) -> None:
        path = self.history_dir / "entry.json"
        path.write_text("{", encoding="utf-8")
        original_text = path.read_text(encoding="utf-8")

        with self.assertRaises(JsonStoreReadError):
            history_store.update_pending_history_status("entry", "failed", "queue sync failed")

        self.assertEqual(path.read_text(encoding="utf-8"), original_text)


if __name__ == "__main__":
    unittest.main()
