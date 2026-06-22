from __future__ import annotations

from dataclasses import dataclass
import csv
import json
import random
from pathlib import Path
from typing import Any

from .character_names import (
    character_entry_payload,
    display_name_ja,
    localized_search_text,
    prompt_safe_character_name,
)
from .config import (
    CHARACTER_CATALOG_ORIGINAL_PATH,
    CHARACTER_CATALOG_ROOT,
    CHARACTER_CATALOG_WAI_PATH,
    ROOT_DIR,
)
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

CUSTOM_CHARACTER_TAGS_PATH = ROOT_DIR / "config" / "custom_character_tags.json"


def _existing_path(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


@dataclass(frozen=True)
class CharacterEntry:
    display_name: str
    prompt_tag: str
    kind: str = "wai"
    id: str = ""
    source: str = "saa_csv"
    trigger_words: list[str] | None = None
    positive_tags: list[str] | None = None
    tags: list[str] | None = None
    identity_prompt: str = ""
    negative_guard: str = ""
    default_lora: str | None = None
    favorite: bool = False
    post_count: int = 0
    verified: bool = True
    notes: str = ""

    @property
    def search_text(self) -> str:
        extra = " ".join(
            [
                self.id,
                self.source,
                " ".join(self.trigger_words or []),
                " ".join(self.positive_tags or []),
                " ".join(self.tags or []),
                self.identity_prompt,
            ]
        )
        return f"{self.display_name} {self.prompt_tag} {self.kind} {extra}".lower()


BLUE_ARCHIVE_ALIASES = ["blue archive", "ブルーアーカイブ", "ブルアカ"]
ZENLESS_ZONE_ZERO_ALIASES = ["zenless zone zero", "ゼンレスゾーンゼロ", "ゼンゼロ", "zzz"]

BLUE_ARCHIVE_COLLAB_PROMPT_PREFIXES = {
    "misaka mikoto",
    "saten ruiko",
    "shokuhou misaki",
}

BLUE_ARCHIVE_NAME_ALIASES = {
    "asuna": ["アスナ", "一之瀬アスナ", "ichinose asuna"],
    "hatsune miku": ["ミク", "初音ミク"],
    "hoshino": ["ホシノ", "小鳥遊ホシノ", "takanashi hoshino"],
    "juri": ["ジュリ", "牛牧ジュリ", "ushimaki juri"],
    "juri (part-time)": ["アルバイト", "arbeit", "part-time job"],
    "kikyou": ["キキョウ", "桐生キキョウ", "kikyo", "kiryuu kikyou"],
    "misaka mikoto": ["ミコト", "御坂美琴"],
    "rei": ["レイ", "野正レイ", "nomasa rei"],
    "rio": ["リオ", "調月リオ", "tsukatsuki rio"],
    "saten ruiko": ["サテン", "ルイコ", "佐天涙子"],
    "shokuhou misaki": ["ショクホウ", "食蜂操祈"],
    "shun": ["シュン", "春原シュン", "sunohara shun"],
}

ZENLESS_ZONE_ZERO_PROMPT_PREFIXES = {
    "alexandrina sebastiane",
    "anby demara",
    "anton ivanov",
    "asaba harumasa",
    "astra yao",
    "ben bigger",
    "billy kid",
    "burnice white",
    "corin wickes",
    "ellen joe",
    "evelyn chevalier",
    "grace howard",
    "hoshimi miyabi",
    "hugo vlad",
    "koleda belobog",
    "komano manato",
    "lucia elowen",
    "luciana de montefio",
    "nekomiya mana",
    "nangong yu",
    "nicole demara",
    "norma hollowell",
    "pan yinhu",
    "piper wheel",
    "pulchra fellini",
    "remielle dan",
    "seth lowell",
    "soldier 0 - anby",
    "starlight - billy kid",
    "tsukishiro yanagi",
    "ukinami yuzuha",
    "velina airgid",
    "vivian banshee",
    "von lycaon",
    "yidhari murphy",
    "zhu yuan",
}


def _append_unique(values: list[str], additions: list[str]) -> None:
    seen = {value.lower() for value in values}
    for addition in additions:
        normalized = addition.strip()
        if not normalized or normalized.lower() in seen:
            continue
        values.append(normalized)
        seen.add(normalized.lower())


def _matches_prompt_prefix(prompt_tag: str, prefixes: set[str]) -> bool:
    return any(
        prompt_tag == prefix or prompt_tag.startswith(f"{prefix} (")
        for prefix in prefixes
    )


def character_search_aliases(prompt_tag: str, display_name: str = "") -> list[str]:
    tag = prompt_tag.lower()
    display = display_name.lower()
    aliases: list[str] = []
    if "(fate" in tag or "fate/" in tag or "fgo" in tag or "grand order" in tag:
        _append_unique(aliases, ["fate", "fgo", "fate grand order"])
    is_blue_archive = (
        "blue archive" in tag
        or "ブルーアーカイブ" in display
        or "ブルアカ" in display
    )
    is_blue_archive_collab = _matches_prompt_prefix(
        tag,
        BLUE_ARCHIVE_COLLAB_PROMPT_PREFIXES,
    )
    if is_blue_archive:
        _append_unique(aliases, BLUE_ARCHIVE_ALIASES)
    if is_blue_archive_collab:
        _append_unique(aliases, BLUE_ARCHIVE_ALIASES)
    if is_blue_archive or is_blue_archive_collab:
        for prefix, name_aliases in BLUE_ARCHIVE_NAME_ALIASES.items():
            if _matches_prompt_prefix(tag, {prefix}):
                _append_unique(aliases, name_aliases)
    if "zenless zone zero" in tag or "ゼンレスゾーンゼロ" in display or "ゼンゼロ" in display:
        _append_unique(aliases, ZENLESS_ZONE_ZERO_ALIASES)
    if _matches_prompt_prefix(tag, ZENLESS_ZONE_ZERO_PROMPT_PREFIXES):
        _append_unique(aliases, ZENLESS_ZONE_ZERO_ALIASES)
    return aliases


def _compact_search_label(value: str) -> str:
    return value.replace(" ", "").strip().lower()


def _search_match_score(entry: CharacterEntry, tokens: list[str]) -> int:
    display = display_name_ja(entry.display_name, entry.prompt_tag).lower()
    display_base = display.split("（", 1)[0].strip()
    prompt = entry.prompt_tag.lower()
    prompt_base = prompt.split(" (", 1)[0].strip()
    safe = prompt_safe_character_name(entry.display_name, entry.prompt_tag).lower()
    labels = [display, display_base, prompt, prompt_base, safe]

    score = 0
    for token in tokens:
        compact_token = _compact_search_label(token)
        compact_labels = [_compact_search_label(label) for label in labels if label]
        if token in {prompt, prompt_base}:
            score += 120
        if any(label == token for label in labels):
            score += 100
        if compact_token and any(label.endswith(compact_token) for label in compact_labels):
            score += 70
        if token and any(label.startswith(token) for label in labels):
            score += 40
        if token and token in display:
            score += 20
    return score


def load_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    path = _existing_path(
        ROOT_DIR / "config" / "character_select_settings.json",
        CHARACTER_CATALOG_ROOT / "settings" / "settings.json",
    )
    if path:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for key, value in raw.items():
                if key in settings:
                    settings[key] = value
        except Exception:
            pass
    return settings


def load_wai_characters() -> list[CharacterEntry]:
    path = _existing_path(CHARACTER_CATALOG_WAI_PATH, CHARACTER_CATALOG_ROOT / "data" / "wai_characters.csv")
    entries: list[CharacterEntry] = []
    if not path:
        return entries
    source = "luna_character_catalog" if path == CHARACTER_CATALOG_WAI_PATH else "legacy_character_catalog"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            display_name = row[0].strip()
            prompt_tag = row[1].strip()
            if display_name and prompt_tag:
                entries.append(
                    CharacterEntry(
                        display_name,
                        prompt_tag,
                        "wai",
                        source=source,
                        tags=character_search_aliases(prompt_tag, display_name),
                    )
                )
    return entries


def load_custom_characters(existing_prompt_tags: set[str]) -> list[CharacterEntry]:
    if not CUSTOM_CHARACTER_TAGS_PATH.exists():
        return []
    try:
        raw = json.loads(CUSTOM_CHARACTER_TAGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    entries: list[CharacterEntry] = []
    seen = set(existing_prompt_tags)
    for item in raw:
        if not isinstance(item, dict):
            continue
        display_name = str(item.get("display_name") or item.get("display_name_ja") or item.get("name") or "").strip()
        prompt_tag = str(item.get("prompt_tag") or "").strip()
        key = prompt_tag.lower()
        if not display_name or not prompt_tag or key in seen:
            continue
        seen.add(key)
        try:
            post_count = int(item.get("post_count") or 0)
        except Exception:
            post_count = 0
        entries.append(
            CharacterEntry(
                display_name=display_name,
                prompt_tag=prompt_tag,
                kind="custom",
                id=str(item.get("id") or prompt_tag),
                source=str(item.get("source") or "custom_character_tags"),
                tags=[
                    str(tag).strip()
                    for tag in item.get("tags") or []
                    if str(tag).strip()
                ]
                + character_search_aliases(prompt_tag, display_name),
                post_count=post_count,
                verified=bool(item.get("verified", False)),
                notes=str(item.get("notes") or ""),
            )
        )
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
    path = _existing_path(CHARACTER_CATALOG_ORIGINAL_PATH, CHARACTER_CATALOG_ROOT / "data" / "original_character.json")
    if not path:
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
        self.custom = load_custom_characters({entry.prompt_tag.lower() for entry in self.wai})
        self.original = load_original_characters()
        self.by_display = {entry.display_name: entry for entry in self.wai}
        self.by_display.update({entry.display_name: entry for entry in self.custom if entry.display_name not in self.by_display})
        self.by_prompt = {entry.prompt_tag: entry for entry in self.wai}
        self.by_prompt.update({entry.prompt_tag: entry for entry in self.custom if entry.prompt_tag not in self.by_prompt})
        self.original_by_display = {entry.display_name: entry for entry in self.original}
        self.original_by_id = {entry.id: entry for entry in self.original if entry.id}

    def search(self, query: str = "", kind: str = "all", limit: int = 80) -> list[dict[str, Any]]:
        return self.search_page(query, kind, limit, 0)["items"]

    def search_page(self, query: str = "", kind: str = "all", limit: int = 80, offset: int = 0) -> dict[str, Any]:
        query = (query or "").strip().lower()
        limit = max(1, int(limit or 80))
        offset = max(0, int(offset or 0))
        pools: list[CharacterEntry] = []
        if kind in ("all", "original"):
            pools.extend(self.original)
        if kind in ("all", "wai"):
            pools.extend(self.wai)
        if kind in ("all", "custom"):
            pools.extend(self.custom)
        if not query:
            matched = pools
        else:
            tokens = [token for token in query.split() if token]
            matched = [
                entry
                for entry in pools
                if all(token in localized_search_text(entry) for token in tokens)
            ]
            matched = [
                entry
                for _, entry in sorted(
                    enumerate(matched),
                    key=lambda item: (
                        -_search_match_score(item[1], tokens),
                        item[0],
                    ),
                )
            ]
        page = matched[offset : offset + limit]
        total = len(matched)
        return {
            "items": [character_entry_payload(entry) for entry in page],
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total,
        }

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
