from __future__ import annotations

import re
from typing import Any

MODE_RANDOM = "random"
MODE_POSITIVE_COMPLETION = "positive_completion"
VALID_MODES = {MODE_RANDOM, MODE_POSITIVE_COMPLETION}
DEFAULT_INSTRUCTIONS = {
    MODE_RANDOM: "衣装、表情、背景、小物をランダムに足す",
    MODE_POSITIVE_COMPLETION: "既存Positiveの意図を保ったまま、不足している描写を英語タグで補う",
}
DEFAULT_INSTRUCTION = DEFAULT_INSTRUCTIONS[MODE_RANDOM]
STRENGTH_REFERENCE_568 = "reference_568"
STRENGTH_LEGACY_568 = "legacy_568"
VALID_STRENGTHS = {"subtle", "standard", "rich", STRENGTH_REFERENCE_568, STRENGTH_LEGACY_568}
MAX_POSITIVE_COMPLETION_TAGS = 12
MAX_POSITIVE_COMPLETION_TAG_CHARS = 220
MAX_RANDOM_TAGS = 12
MAX_RANDOM_TAG_CHARS = 320
MAX_LEGACY_568_RANDOM_TAGS = 14
MAX_LEGACY_568_RANDOM_TAG_CHARS = 320
MAX_RANDOM_TAG_LIMITS_BY_STRENGTH = {
    "subtle": (8, 220),
    "standard": (MAX_RANDOM_TAGS, MAX_RANDOM_TAG_CHARS),
    STRENGTH_REFERENCE_568: (MAX_RANDOM_TAGS, MAX_RANDOM_TAG_CHARS),
    STRENGTH_LEGACY_568: (MAX_LEGACY_568_RANDOM_TAGS, MAX_LEGACY_568_RANDOM_TAG_CHARS),
    "rich": (16, 420),
}
DISALLOWED_RANDOM_TAG_KEYS = {
    "4k",
    "8k",
    "amazing quality",
    "anime art",
    "anime style",
    "best quality",
    "crisp lines",
    "digital painting",
    "high detail",
    "high quality",
    "high resolution",
    "masterpiece",
    "sharp focus",
}
DISALLOWED_RANDOM_TAG_RE = re.compile(
    r"\b("
    r"4k|8k|amazing quality|anime art|anime style|best quality|crisp lines|digital painting|"
    r"high detail|high quality|high resolution|masterpiece|sharp focus"
    r")\b",
    re.IGNORECASE,
)
CHARACTER_IDENTITY_TERMS = {
    "armor",
    "bangs",
    "braid",
    "braids",
    "bun",
    "eye",
    "eyes",
    "hair",
    "hairstyle",
    "horn",
    "horns",
    "iris",
    "katana",
    "lock",
    "locks",
    "ponytail",
    "ponytails",
    "pupil",
    "pupils",
    "spear",
    "staff",
    "strand",
    "strands",
    "sword",
    "tail",
    "twintail",
    "twintails",
    "weapon",
    "weapons",
    "wing",
    "wings",
}
CHARACTER_IDENTITY_RE = re.compile(r"\b(" + "|".join(sorted(CHARACTER_IDENTITY_TERMS, key=len, reverse=True)) + r")\b", re.IGNORECASE)
CHARACTER_MOTIF_TERMS = {
    "armor",
    "armored",
    "banner",
    "blade",
    "bow",
    "chainmail",
    "crossbow",
    "crown",
    "emblem",
    "flag",
    "gauntlet",
    "gauntlets",
    "halo",
    "helmet",
    "holy sword",
    "katana",
    "lance",
    "mace",
    "pauldron",
    "pauldrons",
    "rifle",
    "scimitar",
    "shield",
    "spear",
    "staff",
    "sword",
    "wand",
    "weapon",
    "weapons",
    "wing",
    "wings",
}
CHARACTER_MOTIF_RE = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in sorted(CHARACTER_MOTIF_TERMS, key=len, reverse=True)) + r")s?\b",
    re.IGNORECASE,
)
CHARACTER_MOTIF_OVERRIDE_RE = re.compile(
    r"\b("
    r"armor|armored|banner|blade|bow|chainmail|crossbow|crown|emblem|flag|gauntlet|halo|helmet|"
    r"katana|lance|mace|pauldron|rifle|scimitar|shield|spear|staff|sword|wand|weapon|wings?"
    r")\b|武器|剣|刀|槍|杖|銃|弓|盾|旗|鎧|甲冑|兜|冠|翼|羽|戦闘|バトル|キャラモチーフ|モチーフ",
    re.IGNORECASE,
)
HEAVY_RANDOM_MOTIF_RE = re.compile(
    r"\b("
    r"armor|armored|blade|bodysuit|bow|chainmail|crossbow|daggers?|gauntlets?|greatsword|"
    r"cannon|firearm|guns?|halberd|helmet|katana|lance|mace|pistol|rifle|scimitar|shield|spear|staff|sword|tactical|weapons?"
    r")s?\b",
    re.IGNORECASE,
)
SMALL_PROP_RE = re.compile(r"\b(miniature|small|tiny|toy|wooden|plush|handheld)\b", re.IGNORECASE)
LIGHT_PROP_WEAPON_RE = re.compile(r"\bstaff\b", re.IGNORECASE)
HAIR_EYE_COLOR_RE = re.compile(
    r"\b(auburn|black|blonde|blue|brown|green|golden|gray|grey|pink|purple|red|silver|white)\s+(hair|eyes?)\b",
    re.IGNORECASE,
)
SWIMWEAR_RE = re.compile(r"\b(bikini|swimsuit|two[- ]piece|one[- ]piece)\b", re.IGNORECASE)
POSITIVE_COMPLETION_STRENGTH_HINTS = {
    "subtle": "Add 2 to 4 concise visual tags per item.",
    "standard": "Add 5 to 8 concise visual tags per item.",
    STRENGTH_REFERENCE_568: "Add 5 to 8 concise visual tags per item.",
    STRENGTH_LEGACY_568: "Add 5 to 8 concise visual tags per item.",
    "rich": "Add 8 to 12 vivid visual tags per item without bloating the prompt.",
}
RANDOM_STRENGTH_HINTS = {
    "subtle": "Add 4 to 6 concise tags per item. Preserve the core outfit and character feel; focus on expression, pose nuance, setting, lighting, props, and camera.",
    "standard": "Add 8 to 12 varied tags per item. Preserve explicit outfit tags in the existing prompt, then add compatible outfit layers or accessories, hair accessories, toy-sized props, expressive motion, setting, lighting, and camera. If a bikini or swimsuit is already present, keep it visible and do not replace it with a different outfit; add things around it such as frills, skirt layers, ribbons, cover-ups, props, or background details.",
    STRENGTH_REFERENCE_568: "Use the included #568 reference conditions as a behavioral example. Add 8 to 12 varied tags per item. Preserve explicit outfit tags such as white Bikini, then add compatible outfit layers or accessories, small props, expressive motion, setting, lighting, and camera. Do not invent new hair or eye colors. Do not copy any reference result literally; reproduce the behavior of preserving the base outfit while adding playful coherent variety.",
    STRENGTH_LEGACY_568: "Add 8 to 12 varied tags per item. Push outfit, props, setting, action, lighting, and composition beyond the existing prompt when useful.",
    "rich": "Add 12 to 16 vivid tags per item with bold outfit, prop, setting, action, lighting, and camera changes while keeping the prompt coherent.",
}
REFERENCE_568_CONDITIONS = {
    "source": "Luna ANIMA history #568 behavioral reference",
    "selected_character_context": "Jeanne D'arc from Fate",
    "existing_positive": (
        "masterpiece, best quality, score_7, anime illustration, safe, 1girl, "
        "jeanne d'arc \\(fate\\), An anime illustration of Jeanne D'arc from Fate in a clean, expressive composition., "
        "@gpt-image-2, white Bikini"
    ),
    "instruction": "衣装、表情、背景、小物をランダムに足す",
    "behavior_to_copy": [
        "Keep the base swimsuit or bikini from existing_positive visible.",
        "Add compatible outfit layers or accessories around the base outfit instead of replacing it.",
        "Add a small prop, expressive motion, background, lighting, and camera detail.",
        "Do not invent new hair or eye colors; selected character identity is already handled by the app.",
        "Do not chase a specific color, pattern, or outfit; the reference is about behavior, not a fixed visual theme.",
        "Avoid turning the result into heavy armor or a full battle costume unless the user's current prompt asks for it.",
    ],
}
def _is_legacy_568_feature(feature: dict[str, Any]) -> bool:
    return feature.get("mode") == MODE_RANDOM and feature.get("strength") == STRENGTH_LEGACY_568


def _is_legacy_568_context(context: dict[str, Any]) -> bool:
    return (
        str(context.get("prompt_random_collect_mode") or MODE_RANDOM) == MODE_RANDOM
        and str(context.get("prompt_random_collect_strength") or "standard") == STRENGTH_LEGACY_568
    )


def _clamp_text(value: Any, default: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        text = default
    return text[:limit]
