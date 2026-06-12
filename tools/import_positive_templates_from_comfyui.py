from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_INDEX = Path("generated") / "templates_index.json"


def normalize_prompt_part(value: object) -> str:
    text = " ".join(str(value or "").split())
    return text.strip(" ,")


def compact_prompt_parts(parts: list[object]) -> list[str]:
    return [text for text in (normalize_prompt_part(part) for part in parts or []) if text]


def sanitize_prompt_text(text: object) -> str:
    return ", ".join(compact_prompt_parts(re.split(r",|\n", str(text or ""))))


def slug_text(value: object) -> str:
    text = re.sub(r"\s+", "_", str(value or "").strip().lower())
    text = re.sub(r"[^0-9a-zA-Z_\-\u3040-\u30ff\u3400-\u9fff]+", "_", text)
    return text.strip("_")[:48] or "template"


def infer_category(title: str, prompt: str) -> str:
    haystack = f"{title}\n{prompt}".casefold()
    rules = [
        ("lighting", ["light", "lighting", "neon", "sunset", "rain", "夜", "夕", "朝", "光"]),
        ("scene", ["street", "city", "room", "beach", "ocean", "cafe", "office", "background", "屋", "街", "海", "浜", "室", "背景"]),
        ("pose", ["pose", "standing", "sitting", "lying", "leaning", "from behind", "looking back", "座", "立", "寝", "ポーズ"]),
        ("outfit", ["dress", "shirt", "jacket", "hoodie", "skirt", "jeans", "uniform", "bikini", "outfit", "服", "水着", "制服"]),
        ("composition", ["close-up", "full body", "upper body", "portrait", "angle", "composition", "構図", "全身", "上半身"]),
        ("mood", ["calm", "smile", "confident", "seductive", "relaxed", "雰囲気", "表情"]),
        ("effect", ["sparkle", "glow", "motion", "wind", "effect", "エフェクト"]),
    ]
    for category, needles in rules:
        if any(needle.casefold() in haystack for needle in needles):
            return category
    return "other"


def tags_for_item(category: str, title: str, prompt: str) -> list[str]:
    tags = [category]
    compact = f"{title} {prompt}".casefold()
    candidates = {
        "night": ["night", "neon", "夜"],
        "beach": ["beach", "ocean", "sea", "海"],
        "street": ["street", "city", "街"],
        "room": ["room", "室内", "部屋"],
        "portrait": ["portrait", "close-up", "顔"],
        "fullbody": ["full body", "全身"],
    }
    for tag, needles in candidates.items():
        if any(needle.casefold() in compact for needle in needles):
            tags.append(tag)
    return list(dict.fromkeys(tags))


def make_item(source_item: dict[str, Any], index: int, profile: str) -> dict[str, Any] | None:
    prompt = sanitize_prompt_text(source_item.get("positive_prompt") or source_item.get("positive") or "")
    if not prompt:
        return None
    source_id = str(source_item.get("id") or "").strip()
    title = str(source_item.get("name") or source_item.get("title") or f"Template {index + 1:03d}").strip()
    stable = source_id or hashlib.sha1(f"{title}\n{prompt}".encode("utf-8")).hexdigest()[:12]
    category = infer_category(title, prompt)
    return {
        "id": f"comfy_{slug_text(title)}_{stable[:8]}",
        "title": title,
        "category": category,
        "tags": tags_for_item(category, title, prompt),
        "positive_prompt": prompt,
        "source_template_id": source_id,
        "source_file": str(source_item.get("source_file") or ""),
        "source_positive_node_id": str(source_item.get("positive_node_id") or ""),
        "compatible_profiles": [profile],
        "note": "Imported positive prompt only from ComfyUI_MobilePanel.",
    }


def load_templates(source_root: Path) -> dict[str, Any]:
    source_path = source_root / DEFAULT_SOURCE_INDEX
    with source_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("templates"), list):
        raise ValueError(f"Unsupported templates_index format: {source_path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Import positive prompt templates from ComfyUI_MobilePanel.")
    parser.add_argument("--source", default=r"D:\AI\ComfyUI_MobilePanel", help="ComfyUI_MobilePanel repo root.")
    parser.add_argument("--out", default=r"config\positive_prompt_templates.json", help="Output JSON path.")
    parser.add_argument("--profile", choices=["saa", "anima"], required=True, help="Target profile.")
    args = parser.parse_args()

    source_root = Path(args.source)
    out_path = Path(args.out)
    data = load_templates(source_root)
    items = []
    excluded = []
    for index, source_item in enumerate(data.get("templates", [])):
        item = make_item(source_item, index, args.profile)
        if item:
            items.append(item)
        else:
            excluded.append({"index": index, "reason": "empty_positive_prompt", "source_template_id": source_item.get("id")})

    categories = sorted({item["category"] for item in items})
    payload = {
        "version": 1,
        "source": "ComfyUI_MobilePanel",
        "source_file": str(source_root / DEFAULT_SOURCE_INDEX),
        "source_note": "Positive prompt parts only. Negative, LoRA, model, workflow, seed, size, sampler, hires, and reference settings are not imported.",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target_profile": args.profile,
        "count": len(items),
        "excluded_count": len(excluded),
        "source_mismatch_count": len(data.get("mismatches") or []),
        "categories": categories,
        "items": items,
        "excluded": excluded,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote={out_path}")
    print(f"items={len(items)} excluded={len(excluded)} source_mismatches={payload['source_mismatch_count']}")
    print("categories=" + ", ".join(categories))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
