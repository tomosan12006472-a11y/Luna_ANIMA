from __future__ import annotations

import json
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import _shared_utils
from app import lora_catalog
from app.api import loras as lora_api
from app.config import APP_PIN
from app.main import app
from app.storage.json_store import JsonStoreReadError

catalog_module = importlib.import_module("app.lora.catalog")
diagnostics_module = importlib.import_module("app.lora.diagnostics")
discovery_module = importlib.import_module("app.lora.discovery")
favorites_module = importlib.import_module("app.lora.favorites")
paths_module = importlib.import_module("app.lora.paths")


class LoraCatalogModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.lora_dir = self.root / "loras"
        self.discovery_dir = self.root / "lora_discovery"
        self.lora_dir.mkdir()
        self.discovery_dir.mkdir()

        self.catalog_path = self.root / "lora_catalog_anima.json"
        self.favorites_path = self.root / "lora_favorites_anima.json"

        self._original_values = {
            "paths_dirs": paths_module.COMFYUI_LORA_DIRS,
            "paths_catalog": paths_module.CATALOG_PATH,
            "paths_favorites": paths_module.FAVORITES_PATH,
            "paths_discovery": paths_module.DISCOVERY_DIR,
            "catalog_path": catalog_module.CATALOG_PATH,
            "favorites_path": favorites_module.FAVORITES_PATH,
            "discovery_dir": discovery_module.DISCOVERY_DIR,
            "diagnostics_catalog": diagnostics_module.CATALOG_PATH,
        }

        paths_module.COMFYUI_LORA_DIRS = [self.lora_dir]
        paths_module.CATALOG_PATH = self.catalog_path
        paths_module.FAVORITES_PATH = self.favorites_path
        paths_module.DISCOVERY_DIR = self.discovery_dir
        catalog_module.CATALOG_PATH = self.catalog_path
        favorites_module.FAVORITES_PATH = self.favorites_path
        discovery_module.DISCOVERY_DIR = self.discovery_dir
        diagnostics_module.CATALOG_PATH = self.catalog_path

    def tearDown(self) -> None:
        paths_module.COMFYUI_LORA_DIRS = self._original_values["paths_dirs"]
        paths_module.CATALOG_PATH = self._original_values["paths_catalog"]
        paths_module.FAVORITES_PATH = self._original_values["paths_favorites"]
        paths_module.DISCOVERY_DIR = self._original_values["paths_discovery"]
        catalog_module.CATALOG_PATH = self._original_values["catalog_path"]
        favorites_module.FAVORITES_PATH = self._original_values["favorites_path"]
        discovery_module.DISCOVERY_DIR = self._original_values["discovery_dir"]
        diagnostics_module.CATALOG_PATH = self._original_values["diagnostics_catalog"]
        self._tmp.cleanup()

    def write_catalog(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "app_scope": "anima",
            "items": [
                {
                    "lora_id": "anima_local_style_example_safetensors",
                    "display_name": "Style Example",
                    "file_name": "style_example.safetensors",
                    "relative_path": "style/example.safetensors",
                    "app_scope": "anima",
                    "category": "style",
                    "status": "available",
                    "max_strength": 0.8,
                    "custom_meta": {"kept": True},
                },
                {
                    "lora_id": "other_local_hidden",
                    "display_name": "Hidden",
                    "file_name": "hidden.safetensors",
                    "relative_path": "hidden.safetensors",
                    "app_scope": "unknown",
                    "category": "unknown",
                    "status": "review_required",
                },
            ],
        }
        self.catalog_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    def write_favorites(self) -> None:
        self.favorites_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "app_scope": "anima",
                    "favorites": {
                        "style/example.safetensors": {
                            "lora_id": "anima_local_style_example_safetensors",
                            "relative_path": "style/example.safetensors",
                            "file_name": "style_example.safetensors",
                            "display_name": "Style Example",
                            "app_scope": "anima",
                            "added_at": "2026-06-19T10:00:00",
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_facade_import_exposes_old_function_names(self) -> None:
        for name in [
            "load_catalog",
            "refresh_catalog",
            "selectable_loras",
            "catalog_with_favorites",
            "list_lora_favorites",
            "set_lora_favorite",
            "read_discovery_file",
            "review_candidate",
            "diagnostics",
            "normalize_lora_slots",
        ]:
            self.assertTrue(callable(getattr(lora_catalog, name)), name)

    def test_load_catalog_and_selectable_shape(self) -> None:
        self.write_catalog()

        payload = lora_catalog.load_catalog()
        selectable = lora_catalog.selectable_loras(payload)

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["app_scope"], "anima")
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["max_strength"], 1.0)
        self.assertEqual(payload["items"][0]["custom_meta"], {"kept": True})
        self.assertEqual([item["lora_id"] for item in selectable], ["anima_local_style_example_safetensors"])
        self.assertTrue(selectable[0]["favorite"] is False)

    def test_catalog_json_store_normalizes_invalid_payload_shape(self) -> None:
        self.catalog_path.write_text(
            json.dumps({"schema_version": 1, "app_scope": "anima", "items": "bad", "extra": "keep"}, ensure_ascii=False),
            encoding="utf-8",
        )

        payload = lora_catalog.load_catalog()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["app_scope"], "anima")
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["extra"], "keep")

    def test_refresh_catalog_scans_local_loras_and_preserves_shape(self) -> None:
        anima_dir = self.lora_dir / "anima"
        anima_dir.mkdir()
        (anima_dir / "anima-sample.safetensors").write_bytes(b"fake")
        (self.lora_dir / "rei_oba_v0_step300.safetensors").write_bytes(b"fake")

        payload = lora_catalog.refresh_catalog()
        stored = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        items_by_path = {item["relative_path"]: item for item in payload["items"]}
        selectable_paths = {item["relative_path"] for item in lora_catalog.selectable_loras(payload)}

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["app_scope"], "anima")
        self.assertEqual(stored["schema_version"], 1)
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(items_by_path["anima/anima-sample.safetensors"]["status"], "available")
        self.assertEqual(items_by_path["rei_oba_v0_step300.safetensors"]["app_scope"], "anima")
        self.assertEqual(items_by_path["rei_oba_v0_step300.safetensors"]["status"], "available")
        self.assertIn("anima/anima-sample.safetensors", selectable_paths)
        self.assertIn("rei_oba_v0_step300.safetensors", selectable_paths)

    def test_corrupted_catalog_refresh_does_not_overwrite(self) -> None:
        self.catalog_path.write_text("{", encoding="utf-8")
        original = self.catalog_path.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                lora_catalog.refresh_catalog()

        self.assertEqual(self.catalog_path.read_text(encoding="utf-8"), original)

    def test_catalog_with_favorites_and_list_shape(self) -> None:
        self.write_catalog()
        self.write_favorites()

        payload = lora_catalog.catalog_with_favorites(lora_catalog.load_catalog())
        favorites = lora_catalog.list_lora_favorites()

        self.assertEqual(payload["favorite_count"], 1)
        self.assertTrue(payload["items"][0]["favorite"])
        self.assertEqual(payload["items"][0]["favorite_added_at"], "2026-06-19T10:00:00")
        self.assertTrue(favorites["ok"])
        self.assertEqual(favorites["favorite_count"], 1)
        self.assertEqual(favorites["items"][0]["available"], True)

    def test_set_lora_favorite_add_remove_toggle_shape(self) -> None:
        self.write_catalog()

        query = {"lora_id": "anima_local_style_example_safetensors"}
        added = lora_catalog.set_lora_favorite(query, True)
        toggled_off = lora_catalog.set_lora_favorite(query)
        toggled_on = lora_catalog.set_lora_favorite(query)
        removed = lora_catalog.set_lora_favorite(query, False)

        self.assertTrue(added["ok"])
        self.assertTrue(added["favorite"])
        self.assertEqual(added["item"]["relative_path"], "style/example.safetensors")
        self.assertTrue(toggled_off["ok"])
        self.assertFalse(toggled_off["favorite"])
        self.assertTrue(toggled_off["removed"])
        self.assertTrue(toggled_on["ok"])
        self.assertTrue(toggled_on["favorite"])
        self.assertTrue(removed["ok"])
        self.assertFalse(removed["favorite"])

    def test_set_lora_favorite_preserves_existing_added_at(self) -> None:
        self.write_catalog()
        existing_added_at = "2026-06-19T12:34:56"
        self.favorites_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "app_scope": "anima",
                    "favorites": {
                        "anima_local_style_example_safetensors": {
                            "lora_id": "anima_local_style_example_safetensors",
                            "relative_path": "style/example.safetensors",
                            "file_name": "style_example.safetensors",
                            "display_name": "Style Example",
                            "app_scope": "anima",
                            "added_at": existing_added_at,
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = lora_catalog.set_lora_favorite({"lora_id": "anima_local_style_example_safetensors"}, True)
        stored = json.loads(self.favorites_path.read_text(encoding="utf-8"))

        self.assertTrue(response["favorite"])
        self.assertEqual(response["item"]["added_at"], existing_added_at)
        self.assertEqual(stored["favorites"]["anima_local_style_example_safetensors"]["added_at"], existing_added_at)

    def test_corrupted_lora_favorites_update_does_not_overwrite(self) -> None:
        self.write_catalog()
        self.favorites_path.write_text("{", encoding="utf-8")
        original = self.favorites_path.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                lora_catalog.set_lora_favorite({"lora_id": "anima_local_style_example_safetensors"}, True)

        self.assertEqual(self.favorites_path.read_text(encoding="utf-8"), original)

    def test_discovery_file_and_review_shape(self) -> None:
        characters_path = self.discovery_dir / "fate_characters.json"
        characters_path.write_text(json.dumps({"characters": [{"id": "char_1"}]}, ensure_ascii=False), encoding="utf-8")

        data = lora_catalog.read_discovery_file("fate_characters.json")
        missing = lora_catalog.read_discovery_file("missing.json")
        review = lora_catalog.review_candidate("candidate-1", "approved_anima", "anima", "ok")
        stored = json.loads((self.discovery_dir / "fate_review_queue.json").read_text(encoding="utf-8"))

        self.assertTrue(data["ok"])
        self.assertTrue(data["exists"])
        self.assertEqual(data["characters"], [{"id": "char_1"}])
        self.assertTrue(missing["ok"])
        self.assertFalse(missing["exists"])
        self.assertTrue(review["ok"])
        self.assertEqual(review["review"]["candidate_id"], "candidate-1")
        self.assertEqual(stored["items"][0]["review_status"], "approved_anima")

    def test_discovery_review_preserves_unknown_item_keys(self) -> None:
        review_path = self.discovery_dir / "fate_review_queue.json"
        review_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "scope": "fate",
                    "items": [{"candidate_id": "candidate-1", "extra": {"kept": True}}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        review = lora_catalog.review_candidate("candidate-1", "approved_anima", "anima", "ok")
        stored = json.loads(review_path.read_text(encoding="utf-8"))

        self.assertEqual(review["review"]["extra"], {"kept": True})
        self.assertEqual(stored["items"][0]["extra"], {"kept": True})
        self.assertEqual(stored["items"][0]["review_status"], "approved_anima")

    def test_corrupted_discovery_review_update_does_not_overwrite(self) -> None:
        review_path = self.discovery_dir / "fate_review_queue.json"
        review_path.write_text("{", encoding="utf-8")
        original = review_path.read_text(encoding="utf-8")

        with mock.patch.object(_shared_utils.time, "sleep", lambda _: None):
            with self.assertRaises(JsonStoreReadError):
                lora_catalog.review_candidate("candidate-1", "approved_anima", "anima", "ok")

        self.assertEqual(review_path.read_text(encoding="utf-8"), original)

    def test_api_lora_endpoints_smoke(self) -> None:
        self.write_catalog()
        client = TestClient(app)
        client.post("/api/login", json={"pin": APP_PIN})

        with mock.patch.object(lora_api, "comfy_visible_loras", return_value=["style/example.safetensors"]), mock.patch.object(
            lora_api,
            "load_settings",
            return_value={"api_addr": "127.0.0.1:8188"},
        ):
            catalog_response = client.get("/api/loras/catalog")
            favorites_response = client.get("/api/loras/favorites")
            add_response = client.post("/api/loras/favorites/add", json={"lora_id": "anima_local_style_example_safetensors"})
            remove_response = client.post("/api/loras/favorites/remove", json={"lora_id": "anima_local_style_example_safetensors"})
            diagnostics_response = client.get("/api/loras/diagnostics")
            discovery_response = client.get("/api/loras/discovery/fate/characters")
            review_response = client.post(
                "/api/loras/discovery/fate/review",
                json={"candidate_id": "candidate-api", "review_status": "hold", "app_scope": "anima", "note": "api"},
            )

        self.assertEqual(catalog_response.status_code, 200)
        self.assertTrue(catalog_response.json()["ok"])
        self.assertEqual(len(catalog_response.json()["selectable"]), 1)
        self.assertEqual(favorites_response.status_code, 200)
        self.assertTrue(favorites_response.json()["ok"])
        self.assertEqual(add_response.status_code, 200)
        self.assertTrue(add_response.json()["favorite"])
        self.assertEqual(remove_response.status_code, 200)
        self.assertFalse(remove_response.json()["favorite"])
        self.assertEqual(diagnostics_response.status_code, 200)
        self.assertTrue(diagnostics_response.json()["ok"])
        self.assertEqual(discovery_response.status_code, 200)
        self.assertTrue(discovery_response.json()["ok"])
        self.assertEqual(review_response.status_code, 200)
        self.assertTrue(review_response.json()["ok"])


if __name__ == "__main__":
    unittest.main()
