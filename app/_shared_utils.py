from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any
import uuid


class JsonStoreReadError(RuntimeError):
    pass


LORA_STRENGTH_MAX = 3.0


def clamp_strength(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def clamp_lora_strength(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(LORA_STRENGTH_MAX, number))


def clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def normalize_lora_strengths(item: dict[str, Any], default: float = 1.0) -> dict[str, Any]:
    legacy = clamp_lora_strength(item.get("weight", item.get("strength", item.get("model_strength", item.get("model", default)))), default)
    strength_model = clamp_lora_strength(
        item.get("strength_model", item.get("model_strength", item.get("model_weight", item.get("weight_model", item.get("model", legacy))))),
        legacy,
    )
    strength_clip = clamp_lora_strength(
        item.get("strength_clip", item.get("clip_strength", item.get("clip_weight", item.get("weight_clip", item.get("clip", legacy))))),
        legacy,
    )
    out = dict(item)
    out["strength_model"] = strength_model
    out["strength_clip"] = strength_clip
    out["model_strength"] = strength_model
    out["clip_strength"] = strength_clip
    out["model"] = strength_model
    out["clip"] = strength_clip
    out["weight"] = strength_model
    return out


def normalize_prompt_part(value: object) -> str:
    text = " ".join(str(value or "").split())
    return text.strip(" ,")


def compact_prompt_parts(parts: list[object]) -> list[str]:
    return [text for text in (normalize_prompt_part(part) for part in parts or []) if text]


def compact_join(parts: list[object], separator: str = ", ") -> str:
    return separator.join(compact_prompt_parts(parts))


def sanitize_prompt_text(text: object) -> str:
    return compact_join(re.split(r",|\n", str(text or "")))


def next_node_id(workflow: dict[str, Any], start: int = 9100) -> str:
    node_id = start
    while str(node_id) in workflow:
        node_id += 1
    return str(node_id)


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def read_json_with_retry(path: Path, *, label: str, delay: float = 0.05) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        time.sleep(delay)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as second_error:
            raise JsonStoreReadError(f"{label} is temporarily unreadable") from second_error
