from pathlib import Path
import unittest

from app.config import ROOT_DIR
from app.dynamic_prompt import expand_dynamic_prompt, list_wildcards


CONFIG_DIR = ROOT_DIR / "config" / "dynamic_prompt_wildcards"
EMPTY_USER_DIR = ROOT_DIR / "user_data" / "__missing_dynamic_prompt_wildcards_for_tests__"

GENERAL_OUTFIT_CATEGORIES = (
    "outfit/casual",
    "outfit/formal",
    "outfit/traditional",
    "outfit/work",
    "outfit/sports",
    "outfit/fantasy",
    "outfit/stage",
    "outfit/seasonal",
    "outfit/travel",
    "outfit/home",
)

NSFW_OUTFIT_CATEGORIES = (
    "outfit_nsfw/lingerie",
    "outfit_nsfw/revealing_casual",
    "outfit_nsfw/street",
    "outfit_nsfw/formal",
    "outfit_nsfw/fantasy_cosplay",
    "outfit_nsfw/swim_beach",
    "outfit_nsfw/home_lounge",
    "outfit_nsfw/wet_sheer",
)

APPEARANCE_WILDCARDS = (
    "hair_color",
    "hair_style",
    "eye_color",
    "outfit",
    "outfit_nsfw",
    *GENERAL_OUTFIT_CATEGORIES,
    *NSFW_OUTFIT_CATEGORIES,
)


def wildcard_lines(name: str) -> list[str]:
    path = CONFIG_DIR / f"{name}.txt"
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class DynamicPromptWildcardConfigTests(unittest.TestCase):
    def test_appearance_wildcards_are_listed(self) -> None:
        data = list_wildcards(config_dir=CONFIG_DIR, user_dir=EMPTY_USER_DIR)
        by_name = {item["name"]: item for item in data["items"]}

        self.assertIn("hair_color", by_name)
        self.assertIn("hair_style", by_name)
        self.assertIn("eye_color", by_name)
        self.assertIn("outfit", by_name)
        self.assertIn("outfit_nsfw", by_name)
        for name in (*GENERAL_OUTFIT_CATEGORIES, *NSFW_OUTFIT_CATEGORIES):
            self.assertIn(name, by_name)
        self.assertGreaterEqual(by_name["hair_color"]["count"], 20)
        self.assertGreaterEqual(by_name["hair_style"]["count"], 30)
        self.assertGreaterEqual(by_name["eye_color"]["count"], 15)
        self.assertGreaterEqual(by_name["outfit"]["count"], 10)
        self.assertGreaterEqual(by_name["outfit_nsfw"]["count"], 8)
        for name in (*GENERAL_OUTFIT_CATEGORIES, *NSFW_OUTFIT_CATEGORIES):
            self.assertGreaterEqual(by_name[name]["count"], 15, name)
        self.assertFalse(data["warnings"])

    def test_appearance_wildcards_are_unique(self) -> None:
        for name in APPEARANCE_WILDCARDS:
            lines = wildcard_lines(name)
            self.assertEqual(len(lines), len(set(lines)), name)

    def test_appearance_wildcards_expand(self) -> None:
        result = expand_dynamic_prompt(
            positive_prompt="__hair_color__, __hair_style__, __eye_color__, __outfit__, __outfit_nsfw__",
            negative_prompt="",
            seed=123,
            enabled=True,
            config_dir=CONFIG_DIR,
            user_dir=EMPTY_USER_DIR,
        )

        self.assertFalse(result["warnings"])
        self.assertNotIn("__", result["expanded_positive_prompt"])
        names = [item["name"] for item in result["selections"]]
        self.assertEqual(names[:3], ["hair_color", "hair_style", "eye_color"])
        self.assertIn("outfit", names)
        self.assertIn("outfit_nsfw", names)
        self.assertTrue(any(name.startswith("outfit/") for name in names), names)
        self.assertTrue(any(name.startswith("outfit_nsfw/") for name in names), names)

    def test_outfit_router_wildcards_expand_recursively(self) -> None:
        outfit_result = expand_dynamic_prompt(
            positive_prompt="__outfit__",
            negative_prompt="",
            seed=456,
            enabled=True,
            config_dir=CONFIG_DIR,
            user_dir=EMPTY_USER_DIR,
        )
        nsfw_result = expand_dynamic_prompt(
            positive_prompt="__outfit_nsfw__",
            negative_prompt="",
            seed=456,
            enabled=True,
            config_dir=CONFIG_DIR,
            user_dir=EMPTY_USER_DIR,
        )

        self.assertFalse(outfit_result["warnings"])
        self.assertNotIn("__", outfit_result["expanded_positive_prompt"])
        outfit_names = [item["name"] for item in outfit_result["selections"]]
        self.assertEqual(outfit_names[0], "outfit")
        self.assertGreaterEqual(len(outfit_names), 2)
        self.assertTrue(outfit_names[1].startswith("outfit/"), outfit_names)

        self.assertFalse(nsfw_result["warnings"])
        self.assertNotIn("__", nsfw_result["expanded_positive_prompt"])
        nsfw_names = [item["name"] for item in nsfw_result["selections"]]
        self.assertEqual(nsfw_names[0], "outfit_nsfw")
        self.assertGreaterEqual(len(nsfw_names), 2)
        self.assertTrue(nsfw_names[1].startswith("outfit_nsfw/"), nsfw_names)

    def test_outfit_category_wildcards_expand_directly(self) -> None:
        result = expand_dynamic_prompt(
            positive_prompt="__outfit/casual__, __outfit_nsfw/lingerie__",
            negative_prompt="",
            seed=789,
            enabled=True,
            config_dir=CONFIG_DIR,
            user_dir=EMPTY_USER_DIR,
        )

        self.assertFalse(result["warnings"])
        self.assertNotIn("__", result["expanded_positive_prompt"])
        self.assertEqual(
            [item["name"] for item in result["selections"]],
            ["outfit/casual", "outfit_nsfw/lingerie"],
        )


if __name__ == "__main__":
    unittest.main()
