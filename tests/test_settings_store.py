from __future__ import annotations

import unittest

from app import settings_store


class SettingsStoreTests(unittest.TestCase):
    def test_prompt_random_instruction_favorites_are_sanitized(self) -> None:
        settings = settings_store.sanitize_app_settings(
            {
                "prompt_random_instruction_favorites": [
                    {
                        "id": "fav-1",
                        "label": "水着のまま遊びを足す",
                        "instruction": "水着を維持して、小物と背景を足す",
                        "mode": "bad-mode",
                        "strength": "legacy_568",
                        "include_characters": False,
                        "use_character_motifs": True,
                    },
                    {"instruction": ""},
                    "bad",
                ]
            }
        )

        favorites = settings["prompt_random_instruction_favorites"]
        self.assertEqual(len(favorites), 1)
        self.assertEqual(favorites[0]["id"], "fav-1")
        self.assertEqual(favorites[0]["mode"], "random")
        self.assertEqual(favorites[0]["strength"], "legacy_568")
        self.assertFalse(favorites[0]["include_characters"])
        self.assertFalse(favorites[0]["use_character_motifs"])


if __name__ == "__main__":
    unittest.main()
