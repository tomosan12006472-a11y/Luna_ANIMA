from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_QUEUE = REPO_ROOT / "user_data" / "lora_discovery" / "fate_review_queue.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="fate", choices=["fate"])
    parser.add_argument("--app", default="anima", choices=["saa", "anima"])
    parser.add_argument("--approved-only", action="store_true", default=True)
    parser.parse_args()
    if not REVIEW_QUEUE.exists():
        print(json.dumps({"ok": False, "message": "review queue not found", "path": str(REVIEW_QUEUE)}, ensure_ascii=False, indent=2))
        return 1
    data = json.loads(REVIEW_QUEUE.read_text(encoding="utf-8"))
    approved = [item for item in data.get("items", []) if item.get("review_status") in {"approved", "approved_anima"}]
    print(json.dumps({"ok": False, "status": "download_not_enabled", "approved_count": len(approved), "message": "Download is intentionally disabled until each candidate is reviewed and a concrete destination policy is confirmed."}, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
