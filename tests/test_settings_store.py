from __future__ import annotations

import unittest

from app import settings_store


class SettingsStoreTests(unittest.TestCase):
    def test_official_colorfix_settings_are_sanitized(self) -> None:
        defaulted = settings_store.sanitize_app_settings({"official_loras": {"highres": {"enabled": True}}})
        clamped = settings_store.sanitize_app_settings({"official_loras": {"colorfix": {"enabled": True, "strength": 2}}})

        self.assertIn("colorfix", defaulted["official_loras"])
        self.assertFalse(defaulted["official_loras"]["colorfix"]["enabled"])
        self.assertEqual(defaulted["official_loras"]["colorfix"]["strength"], 0.6)
        self.assertTrue(clamped["official_loras"]["colorfix"]["enabled"])
        self.assertEqual(clamped["official_loras"]["colorfix"]["strength"], 1.0)

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
