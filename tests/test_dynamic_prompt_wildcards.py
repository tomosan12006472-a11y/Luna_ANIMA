from pathlib import Path
import unittest

from app.config import ROOT_DIR
from app.dynamic_prompt import expand_dynamic_prompt, list_wildcards


CONFIG_DIR = ROOT_DIR / "config" / "dynamic_prompt_wildcards"
EMPTY_USER_DIR = ROOT_DIR / "user_data" / "__missing_dynamic_prompt_wildcards_for_tests__"


def wildcard_lines(name: str) -> list[str]:
    path = CONFIG_DIR / f"{name}.txt"
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class DynamicPromptWildcardConfigTests(unittest.TestCase):
    def test_appearance_wildcards_are_listed(self) -> None:
        data = list_wildcards(config_dir=CONFIG_DIR, user_dir=EMPTY_USER_DIR)
        by_name = {item["name"]: item for item in data["items"]}

        self.assertIn("hair_color", by_name)
        self.assertIn("hair_style", by_name)
        self.assertIn("eye_color", by_name)
        self.assertGreaterEqual(by_name["hair_color"]["count"], 20)
        self.assertGreaterEqual(by_name["hair_style"]["count"], 30)
        self.assertGreaterEqual(by_name["eye_color"]["count"], 15)
        self.assertFalse(data["warnings"])

    def test_appearance_wildcards_are_unique(self) -> None:
        for name in ("hair_color", "hair_style", "eye_color"):
            lines = wildcard_lines(name)
            self.assertEqual(len(lines), len(set(lines)), name)

    def test_appearance_wildcards_expand(self) -> None:
        result = expand_dynamic_prompt(
            positive_prompt="__hair_color__, __hair_style__, __eye_color__",
            negative_prompt="",
            seed=123,
            enabled=True,
            config_dir=CONFIG_DIR,
            user_dir=EMPTY_USER_DIR,
        )

        self.assertFalse(result["warnings"])
        self.assertNotIn("__", result["expanded_positive_prompt"])
        self.assertEqual([item["name"] for item in result["selections"]], ["hair_color", "hair_style", "eye_color"])


if __name__ == "__main__":
    unittest.main()
