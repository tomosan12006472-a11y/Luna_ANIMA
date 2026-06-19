from __future__ import annotations

from datetime import datetime
import json
from threading import Lock
import time
from typing import Any

from .._shared_utils import write_json_atomic
from .paths import DISCOVERY_DIR


_DISCOVERY_REVIEW_LOCK = Lock()


def discovery_counts() -> dict[str, Any]:
    result: dict[str, Any] = {
        "fate_character_count": 0,
        "fate_candidate_count": 0,
        "blocked_candidate_count": 0,
        "review_required_count": 0,
        "approved_candidate_count": 0,
        "downloadable_candidate_count": 0,
        "last_discovery_run": None,
    }
    characters_path = DISCOVERY_DIR / "fate_characters.json"
    candidates_path = DISCOVERY_DIR / "fate_candidates_normalized.json"
    review_path = DISCOVERY_DIR / "fate_review_queue.json"
    for path in (characters_path, candidates_path, review_path):
        if path.exists():
            result["last_discovery_run"] = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    if characters_path.exists():
        try:
            characters = json.loads(characters_path.read_text(encoding="utf-8"))
            if isinstance(characters, dict):
                result["fate_character_count"] = len(characters.get("characters") or [])
        except Exception:
            pass
    if candidates_path.exists():
        try:
            data = json.loads(candidates_path.read_text(encoding="utf-8"))
            for character in data.get("characters") or []:
                for candidate in character.get("candidates") or []:
                    result["fate_candidate_count"] += 1
                    status = candidate.get("status")
                    if status == "blocked":
                        result["blocked_candidate_count"] += 1
                    if status == "review_required":
                        result["review_required_count"] += 1
        except Exception:
            pass
    if review_path.exists():
        try:
            data = json.loads(review_path.read_text(encoding="utf-8"))
            for candidate in data.get("items") or []:
                if candidate.get("review_status") in {"approved_anima", "approved"}:
                    result["approved_candidate_count"] += 1
                    if candidate.get("download_url"):
                        result["downloadable_candidate_count"] += 1
        except Exception:
            pass
    return result


def read_discovery_file(name: str) -> dict[str, Any]:
    path = DISCOVERY_DIR / name
    if not path.exists():
        return {"ok": True, "exists": False, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "exists": True, "path": str(path), "error": str(exc)}
    if isinstance(data, dict):
        data.setdefault("ok", True)
        data.setdefault("exists", True)
        data.setdefault("path", str(path))
        return data
    return {"ok": True, "exists": True, "path": str(path), "items": data}


def review_candidate(candidate_id: str, review_status: str, app_scope: str, note: str = "") -> dict[str, Any]:
    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
    path = DISCOVERY_DIR / "fate_review_queue.json"
    with _DISCOVERY_REVIEW_LOCK:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                time.sleep(0.05)
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception as second_error:
                    raise RuntimeError("lora review queue is temporarily unreadable") from second_error
        else:
            data = {"schema_version": 1, "scope": "fate", "items": []}
        items = data.setdefault("items", [])
        found = None
        for item in items:
            if item.get("candidate_id") == candidate_id:
                found = item
                break
        if found is None:
            found = {"candidate_id": candidate_id}
            items.append(found)
        found.update(
            {
                "review_status": review_status,
                "app_scope": app_scope,
                "note": note,
                "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        write_json_atomic(path, data)
        return {"ok": True, "review": found, "path": str(path)}
