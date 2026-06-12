from __future__ import annotations

from dataclasses import dataclass
import csv
import json
import random
from pathlib import Path
from typing import Any

from .config import SAA_ROOT
from .original_characters import load_original_characters as load_original_character_presets


DEFAULT_SETTINGS: dict[str, Any] = {
    "ws_service": True,
    "ws_addr": "0.0.0.0",
    "ws_port": 51028,
    "api_interface": "ComfyUI",
    "api_addr": "127.0.0.1:8188",
    "api_model_sampler": "er_sde",
    "api_model_scheduler": "simple",
    "api_model_file_select": "Anima\\anima-base-v1.0.safetensors",
    "api_model_file_vpred": "Auto",
    "random_seed": -1,
    "cfg": 7,
    "step": 30,
    "width": 1024,
    "height": 1536,
    "batch": 3,
    "character1": "Random",
    "character2": "None",
    "character3": "None",
    "custom_prompt": "",
    "api_prompt": "masterpiece, best quality, amazing quality",
    "api_prompt_right": ":d, selfie",
    "api_neg_prompt": "bad quality,worst quality,worst detail,sketch,censor",
    "prompt_ban": "",
    "lora_slot": [],
}


@dataclass(frozen=True)
class CharacterEntry:
    display_name: str
    prompt_tag: str
    kind: str = "wai"
    id: str = ""
    source: str = "saa_csv"
    trigger_words: list[str] | None = None
    positive_tags: list[str] | None = None
    identity_prompt: str = ""
    negative_guard: str = ""
    default_lora: str | None = None
    favorite: bool = False

    @property
    def search_text(self) -> str:
        extra = " ".join(
            [
                self.id,
                self.source,
                " ".join(self.trigger_words or []),
                " ".join(self.positive_tags or []),
                self.identity_prompt,
            ]
        )
        return f"{self.display_name} {self.prompt_tag} {self.kind} {extra}".lower()


def load_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    path = SAA_ROOT / "settings" / "settings.json"
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for key, value in raw.items():
                if key in settings:
                    settings[key] = value
        except Exception:
            pass
    return settings


def load_wai_characters() -> list[CharacterEntry]:
    path = SAA_ROOT / "data" / "wai_characters.csv"
    entries: list[CharacterEntry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            display_name = row[0].strip()
            prompt_tag = row[1].strip()
            if display_name and prompt_tag:
                entries.append(CharacterEntry(display_name, prompt_tag, "wai", source="saa_csv"))
    return entries


def load_original_characters() -> list[CharacterEntry]:
    entries: list[CharacterEntry] = []
    seen: set[str] = set()
    for item in load_original_character_presets():
        entry = CharacterEntry(
            display_name=str(item.get("display_name") or item.get("id") or ""),
            prompt_tag=str(item.get("prompt_tag") or ", ".join(item.get("positive_tags") or [])),
            kind="original",
            id=str(item.get("id") or ""),
            source="original_character",
            trigger_words=item.get("trigger_words") if isinstance(item.get("trigger_words"), list) else [],
            positive_tags=item.get("positive_tags") if isinstance(item.get("positive_tags"), list) else [],
            identity_prompt=str(item.get("identity_prompt") or ""),
            negative_guard=str(item.get("negative_guard") or ""),
            default_lora=item.get("default_lora"),
            favorite=bool(item.get("favorite", False)),
        )
        entries.append(entry)
        seen.update(value for value in [entry.id, entry.display_name] if value)
    path = SAA_ROOT / "data" / "original_character.json"
    if not path.exists():
        return entries
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return entries
    if isinstance(raw, dict):
        for name, prompt in raw.items():
            if isinstance(name, str) and isinstance(prompt, str):
                legacy_id = name.strip()
                if legacy_id in seen:
                    continue
                entries.append(
                    CharacterEntry(
                        name,
                        prompt,
                        "original",
                        id=legacy_id,
                        source="original_character",
                        trigger_words=[item.strip() for item in prompt.split(",") if item.strip()],
                        positive_tags=[item.strip() for item in prompt.split(",") if item.strip()],
                    )
                )
    return entries


class AnimaCatalog:
    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self.wai = load_wai_characters()
        self.original = load_original_characters()
        self.by_display = {entry.display_name: entry for entry in self.wai}
        self.by_prompt = {entry.prompt_tag: entry for entry in self.wai}
        self.original_by_display = {entry.display_name: entry for entry in self.original}
        self.original_by_id = {entry.id: entry for entry in self.original if entry.id}

    def search(self, query: str = "", kind: str = "all", limit: int = 80) -> list[dict[str, str]]:
        query = (query or "").strip().lower()
        pools: list[CharacterEntry] = []
        if kind in ("all", "original"):
            pools.extend(self.original)
        if kind in ("all", "wai"):
            pools.extend(self.wai)
        if not query:
            matched = pools[:limit]
        else:
            tokens = [token for token in query.split() if token]
            matched = [entry for entry in pools if all(token in entry.search_text for token in tokens)][:limit]
        return [entry.__dict__ for entry in matched]

    def resolve_character_entry(self, value: str, slot: int, seed: int, original: bool = False) -> tuple[str, str, CharacterEntry | None]:
        value = (value or "None").strip()
        if value.lower() == "none":
            return "", "None", None
        original_value = value
        forced_original = value.lower().startswith("original:")
        if forced_original:
            original_value = value.split(":", 1)[1].strip()
        pool = self.original if original or forced_original else self.wai
        if value.lower() == "random":
            if not pool:
                return "", "Random", None
            index_seed = seed if slot == 0 else seed // 3 if slot == 1 else seed // 7 if slot == 2 else 4294967296 - seed
            entry = pool[index_seed % len(pool)]
            return entry.prompt_tag, entry.display_name, entry
        if original or forced_original:
            entry = self.original_by_id.get(original_value) or self.original_by_display.get(original_value)
        else:
            entry = self.by_display.get(value) or self.by_prompt.get(value)
        if not entry:
            return value, value, None
        return entry.prompt_tag, entry.display_name, entry

    def resolve_character(self, value: str, slot: int, seed: int, original: bool = False) -> tuple[str, str]:
        tag, name, _entry = self.resolve_character_entry(value, slot, seed, original)
        return tag, name


catalog = AnimaCatalog()


def generate_seed(seed: int | None) -> int:
    if seed is None or int(seed) < 0:
        return random.randint(0, 4294967295)
    return int(seed)
