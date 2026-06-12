from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


DEFAULT_DICTIONARY_DIR = Path(r"D:\AI\PromptDictionaryData\sd-webui-prompt-dictionary\data")
MAIN_TSV = "prompt_dictionary.tsv"
EXTRA_TSV = "danbooru_extra.tsv"
SECTION_NAME = "SEX/体位"

CURATED_POSITION_TAGS = {
    "69",
    "amazon_position",
    "bent_over",
    "boy_on_top",
    "cowgirl_position",
    "doggystyle",
    "folded",
    "full_nelson",
    "legs_over_head",
    "legs_up",
    "mating_press",
    "missionary",
    "on_side",
    "prone_bone",
    "reverse_cowgirl_position",
    "sex_from_behind",
    "spooning",
    "standing_sex",
    "straddling",
    "suspended_congress",
    "top-down_bottom-up",
    "upright_straddle",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def to_int(value: Any) -> int:
    try:
        return int(float(str(value or "0").replace(",", "")))
    except Exception:
        return 0


def has_position_section(row: dict[str, str]) -> bool:
    section = str(row.get("dictionary_section") or "")
    aliases = str(row.get("aliases") or "")
    values = [part.strip() for part in f"{section},{aliases}".split(",")]
    return SECTION_NAME in values


def read_position_candidates(data_dir: Path) -> list[dict[str, str]]:
    candidates_by_tag: dict[str, dict[str, str]] = {}
    for filename in (MAIN_TSV, EXTRA_TSV):
        path = data_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter="\t")
            for row in reader:
                tag = str(row.get("tag") or "").strip()
                if not tag or not (has_position_section(row) or tag in CURATED_POSITION_TAGS):
                    continue
                key = tag.casefold()
                current = candidates_by_tag.get(key)
                if current and to_int(current.get("post_count")) >= to_int(row.get("post_count")):
                    continue
                candidates_by_tag[key] = {
                    "tag": tag,
                    "ja": str(row.get("ja") or ""),
                    "dictionary_section": str(row.get("dictionary_section") or ""),
                    "post_count": str(row.get("post_count") or "0"),
                    "source": filename,
                    "wildcard_include": "1" if tag in CURATED_POSITION_TAGS else "0",
                }
    return sorted(
        candidates_by_tag.values(),
        key=lambda row: (-to_int(row.get("post_count")), row.get("tag", "")),
    )


def write_candidates(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["tag", "ja", "dictionary_section", "post_count", "source", "wildcard_include"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_wildcard(path: Path, rows: list[dict[str, str]]) -> None:
    included = [row["tag"] for row in rows if row.get("wildcard_include") == "1"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(included)) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the __position__ dynamic prompt wildcard from the prompt dictionary.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DICTIONARY_DIR)
    parser.add_argument("--wildcard-out", type=Path, default=repo_root() / "config" / "dynamic_prompt_wildcards" / "position.txt")
    parser.add_argument("--candidates-out", type=Path, default=repo_root() / "config" / "dynamic_prompt_wildcards" / "position_candidates.tsv")
    args = parser.parse_args()

    rows = read_position_candidates(args.data_dir)
    if not rows:
        raise SystemExit(f"No {SECTION_NAME} candidates found in {args.data_dir}")

    write_candidates(args.candidates_out, rows)
    write_wildcard(args.wildcard_out, rows)
    included_count = sum(1 for row in rows if row.get("wildcard_include") == "1")
    print(f"candidates: {len(rows)} -> {args.candidates_out}")
    print(f"wildcard entries: {included_count} -> {args.wildcard_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
