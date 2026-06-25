from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app import history_store, prompt_random_collect
from app.generation_helpers import prompt_random_collect_context_request
from app.payload_builder import build_prompts
from app.prompt_random import context as prompt_random_context
from app.prompt_random import fallback as prompt_random_fallback
from app.prompt_random import sanitizer as prompt_random_sanitizer
from app.prompt_random import service as prompt_random_service


class PromptRandomCollectTests(unittest.TestCase):
    def test_facade_reexports_legacy_symbols(self) -> None:
        for name in (
            "PromptRandomCollectSettings",
            "POSITIVE_COMPLETION_STRENGTH_HINTS",
            "SCORE_TAG_RE",
            "split_prompt_tags",
            "normalize_tag_prompt",
            "_random_tag_key",
            "_identity_terms",
            "_character_reference_keys",
            "_character_motif_override_requested",
        ):
            self.assertTrue(hasattr(prompt_random_collect, name), name)

    def test_facade_collect_uses_legacy_patch_points(self) -> None:
        feature = {"enabled": True, "mode": "random", "strength": "standard"}
        contexts = [{"index": 0, "seed": 1, "existing_positive": "1girl"}]

        with mock.patch.object(prompt_random_collect, "_provider_config", side_effect=RuntimeError("provider patch used")):
            with self.assertRaisesRegex(RuntimeError, "provider patch used"):
                prompt_random_collect.collect_prompt_random_tags({}, feature=feature, contexts=contexts, app_scope="anima")

        with mock.patch.object(
            prompt_random_collect,
            "_provider_config",
            return_value={
                "enabled": True,
                "provider": "lmstudio",
                "base_url": "http://example.test/v1",
                "model": "qwen",
                "temperature": 0.85,
                "max_tokens": 1800,
                "timeout_sec": 30,
            },
        ), mock.patch.object(prompt_random_collect, "_ensure_ready", return_value={"reachable": True, "models": ["qwen"]}), mock.patch.object(
            prompt_random_collect,
            "_json_request",
            return_value={"choices": [{"message": {"content": "{\"items\":[{\"index\":0,\"tags\":\"red dress\"}]}"}}]},
        ):
            result = prompt_random_collect.collect_prompt_random_tags({}, feature=feature, contexts=contexts, app_scope="anima")

        self.assertTrue(result["ok"])
        self.assertEqual(result["generated_items"][0]["tags"], "red dress")

    def test_sanitize_request_defaults_instruction_and_strength(self) -> None:
        result = prompt_random_collect.sanitize_prompt_random_collect_request({"enabled": True, "strength": "bad"})
        self.assertTrue(result["enabled"])
        self.assertEqual(result["mode"], "random")
        self.assertEqual(result["instruction"], prompt_random_collect.DEFAULT_INSTRUCTION)
        self.assertEqual(result["strength"], "standard")
        self.assertTrue(result["include_characters"])
        self.assertTrue(result["use_character_motifs"])

    def test_sanitize_request_accepts_positive_completion_mode(self) -> None:
        result = prompt_random_collect.sanitize_prompt_random_collect_request(
            {"enabled": True, "mode": "positive_completion", "instruction": ""}
        )
        self.assertTrue(result["enabled"])
        self.assertEqual(result["mode"], "positive_completion")
        self.assertEqual(result["instruction"], prompt_random_collect.DEFAULT_INSTRUCTIONS["positive_completion"])

    def test_sanitize_request_accepts_reference_568_strength(self) -> None:
        result = prompt_random_collect.sanitize_prompt_random_collect_request({"enabled": True, "strength": "reference_568"})

        self.assertEqual(result["strength"], "reference_568")

    def test_sanitize_request_accepts_legacy_568_strength(self) -> None:
        result = prompt_random_collect.sanitize_prompt_random_collect_request({"enabled": True, "strength": "legacy_568"})

        self.assertEqual(result["strength"], "legacy_568")

    def test_sanitize_request_can_disable_character_context(self) -> None:
        result = prompt_random_collect.sanitize_prompt_random_collect_request(
            {"enabled": True, "include_characters": False, "use_character_motifs": True}
        )
        self.assertFalse(result["include_characters"])
        self.assertFalse(result["use_character_motifs"])

    def test_sanitize_request_can_enable_character_motifs_with_character_context(self) -> None:
        result = prompt_random_collect.sanitize_prompt_random_collect_request(
            {"enabled": True, "include_characters": True, "use_character_motifs": True}
        )
        self.assertTrue(result["include_characters"])
        self.assertTrue(result["use_character_motifs"])

    def test_user_prompt_marks_character_context_as_intentionally_omitted(self) -> None:
        feature = prompt_random_collect.sanitize_prompt_random_collect_request({"enabled": True, "include_characters": False})
        payload = json.loads(prompt_random_collect._user_prompt(feature, [{"index": 0, "existing_positive": "1girl"}], "anima"))

        self.assertFalse(payload["character_context_enabled"])
        self.assertFalse(payload["character_motifs_enabled"])
        self.assertIn("intentionally omitted", payload["character_context_rule"])

    def test_user_prompt_random_mode_exposes_strength_and_motif_rules(self) -> None:
        feature = prompt_random_collect.sanitize_prompt_random_collect_request({"enabled": True, "mode": "random", "strength": "standard"})
        payload = json.loads(prompt_random_collect._user_prompt(feature, [{"index": 0, "existing_positive": "1girl, white bikini"}], "anima"))

        self.assertIn("Preserve explicit outfit tags", payload["strength_hint"])
        self.assertTrue(payload["character_motifs_enabled"])
        self.assertIn("allowed", payload["character_motif_rule"])
        self.assertIn("Creative variance is desirable", prompt_random_collect._system_prompt("anima", "random"))

    def test_user_prompt_reference_568_strength_includes_reference_conditions(self) -> None:
        feature = prompt_random_collect.sanitize_prompt_random_collect_request(
            {"enabled": True, "mode": "random", "strength": "reference_568"}
        )
        payload = json.loads(prompt_random_collect._user_prompt(feature, [{"index": 0, "existing_positive": "1girl, white bikini"}], "anima"))

        self.assertEqual(payload["strength"], "reference_568")
        self.assertIn("#568 reference conditions", payload["strength_hint"])
        self.assertIn("Do not invent new hair or eye colors", payload["strength_hint"])
        self.assertIn("reference_568_conditions", payload)
        self.assertIn("white Bikini", payload["reference_568_conditions"]["existing_positive"])
        self.assertNotIn("generated_tags", payload["reference_568_conditions"])
        self.assertIn("not a fixed visual theme", " ".join(payload["reference_568_conditions"]["behavior_to_copy"]))

    def test_legacy_568_prompt_recreates_old_qwen_request_shape(self) -> None:
        feature = prompt_random_collect.sanitize_prompt_random_collect_request(
            {
                "enabled": True,
                "mode": "random",
                "instruction": "this should be ignored for legacy",
                "strength": "legacy_568",
                "include_characters": True,
                "use_character_motifs": True,
            }
        )
        payload = json.loads(
            prompt_random_collect._user_prompt(
                feature,
                [{"index": 0, "seed": 568, "characters": ["Jeanne"], "existing_positive": "current positive only"}],
                "anima",
            )
        )

        self.assertEqual(payload["mode"], "random")
        self.assertEqual(payload["instruction"], prompt_random_collect.DEFAULT_INSTRUCTIONS["random"])
        self.assertEqual(payload["strength"], "standard")
        self.assertEqual(
            payload["strength_hint"],
            "Add 8 to 12 varied tags per item. Push outfit, props, setting, action, lighting, and composition beyond the existing prompt when useful.",
        )
        self.assertEqual(payload["items"][0]["existing_positive"], "current positive only")
        self.assertNotIn("character_motifs_enabled", payload)
        self.assertNotIn("character_motif_rule", payload)
        self.assertNotIn("batch_diversity_rule", payload)
        self.assertNotIn("reference_568_conditions", payload)

    def test_legacy_568_system_prompt_recreates_old_random_prompt(self) -> None:
        system_prompt = prompt_random_collect._system_prompt("anima", "random", "legacy_568")

        self.assertIn("Keep each tags string compact, normally under 320 characters for standard strength", system_prompt)
        self.assertIn("You may add alternate costume layers, unusual props, and new settings", system_prompt)
        self.assertNotIn("character_motifs_enabled", system_prompt)
        self.assertNotIn("For subtle and standard strength", system_prompt)

    def test_character_context_disabled_removes_character_tags_from_existing_positive_context(self) -> None:
        request = {
            "character1": "scathach (fate)",
            "character2": "None",
            "character3": "None",
            "original_character": "None",
            "rating": "safe",
            "quality_preset": "standard",
            "meta_prompt": "anime illustration",
            "positive_prompt": "1girl, solo, cafe, maid outfit",
            "negative_prompt": "",
            "negative_prompt_raw": "",
            "negative_prompt_mode": "append",
            "prompt_random_collect": {"enabled": True, "include_characters": False},
        }
        regular_positive = build_prompts(request)["positive"].lower()
        context_positive = build_prompts(prompt_random_collect_context_request(request, include_characters=False))["positive"].lower()

        self.assertIn("scathach", regular_positive)
        self.assertIn("fate", regular_positive)
        self.assertNotIn("scathach", context_positive)
        self.assertNotIn("fate", context_positive)
        self.assertIn("cafe", context_positive)

    def test_context_module_removes_selected_characters_when_disabled(self) -> None:
        request = {
            "character1": "scathach (fate)",
            "character2": "None",
            "character3": "None",
            "original_character": "None",
            "rating": "safe",
            "quality_preset": "standard",
            "meta_prompt": "anime illustration",
            "positive_prompt": "1girl, solo, cafe, maid outfit",
            "negative_prompt": "",
            "negative_prompt_raw": "",
            "negative_prompt_mode": "append",
            "prompt_random_collect": {"enabled": True, "include_characters": False},
        }

        contexts = prompt_random_context.build_prompt_random_collect_contexts(
            [request],
            include_characters=False,
            build_prompts_func=build_prompts,
        )

        self.assertEqual(contexts[0]["characters"], [])
        self.assertEqual(contexts[0]["character_metadata"], [])
        self.assertTrue(contexts[0]["suppress_character_identity"])
        self.assertNotIn("scathach", contexts[0]["existing_positive"].lower())
        self.assertIn("cafe", contexts[0]["existing_positive"].lower())

    def test_normalize_items_removes_disallowed_syntax_and_existing_tags(self) -> None:
        contexts = [{"index": 0, "seed": 11, "existing_positive": "white hair, blue eyes"}]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "white_hair, blue_eyes, red_dress, <lora:test:1>, __pose__"}]},
            contexts,
        )
        self.assertEqual(result[0]["tags"], "red dress")

    def test_normalize_items_strips_character_identity_tags_when_context_is_suppressed(self) -> None:
        contexts = [{"index": 0, "existing_positive": "1girl, cafe", "suppress_character_identity": True}]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "blue hair, messy bun, red apron, sword, coffee cup, soft sunlight"}]},
            contexts,
        )
        self.assertEqual(result[0]["tags"], "red apron, coffee cup, soft sunlight")

    def test_normalize_items_keeps_identity_tags_when_existing_positive_allows_them(self) -> None:
        contexts = [{"index": 0, "existing_positive": "1girl, blue hair, ponytail", "suppress_character_identity": True}]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "long hair, loose ponytail, red apron, sword"}]},
            contexts,
        )
        self.assertEqual(result[0]["tags"], "long hair, loose ponytail, red apron")

    def test_normalize_items_strips_character_motifs_when_disabled(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "1girl, white bikini",
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "standard",
                "prompt_random_collect_use_character_motifs": False,
                "prompt_random_collect_instruction": "衣装、表情、背景、小物をランダムに足す",
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {
                "items": [
                    {
                        "index": 0,
                        "tags": "blue hair, golden eyes, golden halo, silver armor, standing on a beach, soft rim lighting, glass of lemonade",
                    }
                ]
            },
            contexts,
        )

        self.assertEqual(result[0]["tags"], "blue hair, golden eyes, standing on a beach, soft rim lighting, glass of lemonade")

    def test_normalize_items_keeps_character_motifs_when_enabled(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "1girl, white bikini",
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "standard",
                "prompt_random_collect_use_character_motifs": True,
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "golden halo, red cape, standing on a beach"}]},
            contexts,
        )

        self.assertEqual(result[0]["tags"], "golden halo, red cape, standing on a beach")

    def test_standard_random_filters_heavy_battle_motifs_even_when_motifs_enabled(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "1girl, white bikini",
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "standard",
                "prompt_random_collect_use_character_motifs": True,
                "prompt_random_collect_instruction": "衣装、表情、背景、小物をランダムに足す",
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {
                "items": [
                    {
                        "index": 0,
                        "tags": "red checkered frilly dress, holding a miniature wooden horse, holding a small wooden staff, small silver halberd, energy pistol, silver sword, golden armor, sunset sky",
                    }
                ]
            },
            contexts,
        )

        self.assertEqual(
            result[0]["tags"],
            "red checkered frilly dress, holding a miniature wooden horse, holding a small wooden staff, sunset sky",
        )

    def test_standard_random_filters_swimwear_replacements_when_bikini_exists(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "@gpt-image-2, white Bikini",
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "standard",
                "prompt_random_collect_use_character_motifs": True,
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {
                "items": [
                    {
                        "index": 0,
                        "tags": "pink two-piece swimsuit, red checkered frilly skirt, holding a miniature wooden horse, sunset sky",
                    }
                ]
            },
            contexts,
        )

        self.assertEqual(result[0]["tags"], "red checkered frilly skirt, holding a miniature wooden horse, sunset sky")

    def test_rich_random_keeps_heavy_battle_motifs_when_motifs_enabled(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "1girl, white bikini",
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "rich",
                "prompt_random_collect_use_character_motifs": True,
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "silver sword, golden armor, stormy battlefield"}]},
            contexts,
        )

        self.assertEqual(result[0]["tags"], "silver sword, golden armor, stormy battlefield")

    def test_normalize_items_keeps_character_motifs_when_instruction_requests_them(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "1girl, white bikini",
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "standard",
                "prompt_random_collect_use_character_motifs": False,
                "prompt_random_collect_instruction": "武器と鎧をランダムに足す",
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "golden halo, silver armor, standing on a beach"}]},
            contexts,
        )

        self.assertEqual(result[0]["tags"], "golden halo, silver armor, standing on a beach")

    def test_normalize_items_removes_generated_character_name_tags(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "1girl, jeanne d'arc \\(fate\\), white bikini",
                "characters": [{"prompt_tag": "jeanne d'arc (fate)", "prompt_safe_name": "Jeanne D'arc from Fate"}],
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "standard",
                "prompt_random_collect_use_character_motifs": True,
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "jeanne d'arc, fate, snowy cathedral, soft rim lighting"}]},
            contexts,
        )

        self.assertEqual(result[0]["tags"], "snowy cathedral, soft rim lighting")

    def test_normalize_items_removes_partial_generated_character_name_tags(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "1girl, jeanne d'arc alter \\(fate\\), white bikini",
                "characters": [{"prompt_tag": "jeanne d'arc alter (fate)", "prompt_safe_name": "Jeanne D'arc Alter from Fate"}],
                "character_metadata": [],
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "standard",
                "prompt_random_collect_use_character_motifs": True,
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "jeanne d'arc alter, sunset beach, playful smile"}]},
            contexts,
        )

        self.assertEqual(result[0]["tags"], "sunset beach, playful smile")

    def test_normalize_items_removes_character_name_tags_from_metadata_context(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "1girl, jeanne d'arc alter \\(fate\\), white bikini",
                "characters": ["ジャンヌ・ダルク〔オルタ〕（Fate）"],
                "character_metadata": [{"prompt_tag": "jeanne d'arc alter (fate)", "prompt_safe_name": "Jeanne D'arc Alter from Fate"}],
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "standard",
                "prompt_random_collect_use_character_motifs": True,
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "jeanne d'arc alter (fate), stormy sky, crimson cloak"}]},
            contexts,
        )

        self.assertEqual(result[0]["tags"], "stormy sky, crimson cloak")

    def test_normalize_items_filters_score_quality_and_clamps_long_tags(self) -> None:
        contexts = [{"index": 0, "existing_positive": ""}]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {
                "items": [
                    {
                        "index": 0,
                        "tags": (
                            "score_9, masterpiece, best quality, soft sunlight, ceramic cup, wooden table, "
                            "steam rising, cozy atmosphere, shallow depth of field, pastel walls, "
                            "8k resolution, flower vase, lace apron, warm shadows, window reflection, extra detail"
                        ),
                    }
                ]
            },
            contexts,
        )

        tags = result[0]["tags"]
        self.assertNotIn("score_9", tags)
        self.assertNotIn("masterpiece", tags)
        self.assertNotIn("best quality", tags)
        self.assertNotIn("8k", tags)
        self.assertLessEqual(len(tags), prompt_random_collect.MAX_RANDOM_TAG_CHARS)
        self.assertLessEqual(len(tags.split(",")), prompt_random_collect.MAX_RANDOM_TAGS)

    def test_sanitizer_module_filters_quality_score_and_overlong_tags(self) -> None:
        raw_tags = (
            "score_9, masterpiece, best quality, soft sunlight, ceramic cup, wooden table, "
            "steam rising, cozy atmosphere, shallow depth of field, pastel walls, "
            "8k resolution, flower vase, lace apron, warm shadows, window reflection, extra detail"
        )

        tags = prompt_random_sanitizer.sanitize_generated_random_tags(raw_tags, {"existing_positive": ""})

        self.assertNotIn("score_9", tags)
        self.assertNotIn("masterpiece", tags)
        self.assertNotIn("best quality", tags)
        self.assertNotIn("8k", tags)
        self.assertLessEqual(len(tags), prompt_random_collect.MAX_RANDOM_TAG_CHARS)
        self.assertLessEqual(len(tags.split(",")), prompt_random_collect.MAX_RANDOM_TAGS)

    def test_random_mode_preserves_reference_level_tag_span(self) -> None:
        reference_tags = (
            "golden halo floating above head, translucent blue energy cloak, holding a glowing crystal orb, "
            "kneeling on stone steps, dramatic backlighting, lens flare, intricate metal armor details, "
            "focused intense gaze, particles swirling around, ethereal atmosphere, cool color palette, wide angle shot"
        )
        contexts = [
            {
                "index": 0,
                "existing_positive": "",
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "rich",
                "prompt_random_collect_use_character_motifs": True,
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items({"items": [{"index": 0, "tags": reference_tags}]}, contexts)

        self.assertEqual(result[0]["tags"], reference_tags)
        self.assertGreater(len(result[0]["tags"]), prompt_random_collect.MAX_POSITIVE_COMPLETION_TAG_CHARS)
        self.assertLessEqual(len(result[0]["tags"]), prompt_random_collect.MAX_RANDOM_TAG_CHARS)

    def test_standard_random_preserves_true_568_reference_tags(self) -> None:
        reference_tags = (
            "red and black checkered frilly dress, pigtails with gold clips, holding a miniature wooden horse, "
            "spinning mid-air, dynamic motion blur, sunset sky background, warm golden hour glow, sparkling dust motes, "
            "confident playful expression, flowing ribbons, high contrast shadows, telephoto lens compression"
        )
        contexts = [
            {
                "index": 0,
                "existing_positive": "@gpt-image-2, white Bikini",
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "standard",
                "prompt_random_collect_use_character_motifs": True,
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items({"items": [{"index": 0, "tags": reference_tags}]}, contexts)

        self.assertEqual(result[0]["tags"], reference_tags)
        self.assertLessEqual(len(result[0]["tags"]), prompt_random_collect.MAX_RANDOM_TAG_CHARS)

    def test_reference_568_strength_uses_standard_random_limits(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "@gpt-image-2, white Bikini",
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "reference_568",
                "prompt_random_collect_use_character_motifs": True,
            }
        ]

        self.assertEqual(
            prompt_random_collect.prompt_random_limits(contexts[0]),
            (prompt_random_collect.MAX_RANDOM_TAGS, prompt_random_collect.MAX_RANDOM_TAG_CHARS),
        )

    def test_reference_568_strength_filters_new_hair_and_eye_colors(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "@gpt-image-2, white Bikini",
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "reference_568",
                "prompt_random_collect_use_character_motifs": True,
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {
                "items": [
                    {
                        "index": 0,
                        "tags": "blue hair, red eyes, ribbon hair accessory, holding a miniature wooden horse, sunset sky",
                    }
                ]
            },
            contexts,
        )

        self.assertEqual(result[0]["tags"], "ribbon hair accessory, holding a miniature wooden horse, sunset sky")

    def test_legacy_568_strength_uses_old_limits_and_filters_only_old_safety_set(self) -> None:
        contexts = [
            {
                "index": 0,
                "existing_positive": "@gpt-image-2, white Bikini",
                "characters": [{"prompt_tag": "jeanne d'arc (fate)", "prompt_safe_name": "Jeanne D'arc from Fate"}],
                "prompt_random_collect_mode": "random",
                "prompt_random_collect_strength": "legacy_568",
                "prompt_random_collect_use_character_motifs": False,
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {
                "items": [
                    {
                        "index": 0,
                        "tags": "masterpiece, pink two-piece swimsuit, jeanne d'arc, silver sword, golden armor, blue hair, sunset sky",
                    }
                ]
            },
            contexts,
        )

        self.assertEqual(
            result[0]["tags"],
            "pink two-piece swimsuit, jeanne d'arc, silver sword, golden armor, blue hair, sunset sky",
        )
        self.assertEqual(
            prompt_random_collect.prompt_random_limits(contexts[0]),
            (prompt_random_collect.MAX_LEGACY_568_RANDOM_TAGS, prompt_random_collect.MAX_LEGACY_568_RANDOM_TAG_CHARS),
        )

    def test_legacy_568_strength_keeps_repeated_tags_across_batch(self) -> None:
        contexts = [
            {"index": 0, "prompt_random_collect_mode": "random", "prompt_random_collect_strength": "legacy_568"},
            {"index": 1, "prompt_random_collect_mode": "random", "prompt_random_collect_strength": "legacy_568"},
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {
                "items": [
                    {"index": 0, "tags": "golden halo, sunset sky, playful smile"},
                    {"index": 1, "tags": "golden halo, snowy cathedral, playful smile, soft rim lighting"},
                ]
            },
            contexts,
        )

        self.assertEqual(result[0]["tags"], "golden halo, sunset sky, playful smile")
        self.assertEqual(result[1]["tags"], "golden halo, snowy cathedral, playful smile, soft rim lighting")

    def test_positive_completion_keeps_tighter_tag_span(self) -> None:
        reference_tags = (
            "golden halo floating above head, translucent blue energy cloak, holding a glowing crystal orb, "
            "kneeling on stone steps, dramatic backlighting, lens flare, intricate metal armor details, "
            "focused intense gaze, particles swirling around, ethereal atmosphere, cool color palette, wide angle shot"
        )
        contexts = [
            {
                "index": 0,
                "existing_positive": "",
                "prompt_random_collect_mode": "positive_completion",
                "prompt_random_collect_strength": "standard",
            }
        ]
        result = prompt_random_collect.normalize_prompt_random_collect_items({"items": [{"index": 0, "tags": reference_tags}]}, contexts)

        self.assertLessEqual(len(result[0]["tags"]), prompt_random_collect.MAX_POSITIVE_COMPLETION_TAG_CHARS)
        self.assertLess(len(result[0]["tags"]), len(reference_tags))

    def test_normalize_items_requires_one_item_per_context(self) -> None:
        contexts = [{"index": 0}, {"index": 1}]
        with self.assertRaises(ValueError):
            prompt_random_collect.normalize_prompt_random_collect_items({"items": [{"index": 0, "tags": "red dress"}]}, contexts)

    def test_normalize_items_recovers_duplicate_tag_sets_with_fallback(self) -> None:
        contexts = [{"index": 0}, {"index": 1}]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {"items": [{"index": 0, "tags": "red dress"}, {"index": 1, "tags": "red dress"}]},
            contexts,
        )

        self.assertEqual(result[0]["tags"], "red dress")
        self.assertTrue(result[1]["tags"])
        self.assertNotEqual(result[0]["tags"], result[1]["tags"])

    def test_normalize_items_removes_repeated_tags_across_batch(self) -> None:
        contexts = [{"index": 0}, {"index": 1}]
        result = prompt_random_collect.normalize_prompt_random_collect_items(
            {
                "items": [
                    {"index": 0, "tags": "golden halo, sunset sky, playful smile"},
                    {"index": 1, "tags": "golden halo, snowy cathedral, playful smile, soft rim lighting"},
                ]
            },
            contexts,
        )

        self.assertEqual(result[0]["tags"], "golden halo, sunset sky, playful smile")
        self.assertEqual(result[1]["tags"], "snowy cathedral, soft rim lighting")

    def test_collect_items_falls_back_to_single_item_calls_after_batch_failures(self) -> None:
        contexts = [{"index": 0, "existing_positive": ""}, {"index": 1, "existing_positive": ""}]
        calls: list[int] = []

        def fake_once(config, model, request_config, call_contexts, app_scope):
            calls.append(len(call_contexts))
            if len(call_contexts) > 1:
                raise ValueError("bad batch json")
            index = call_contexts[0]["index"]
            return [{"index": index, "tags": f"tag {index}"}]

        with mock.patch.object(prompt_random_collect, "_collect_prompt_random_items_once", side_effect=fake_once):
            items, strategy = prompt_random_collect._collect_prompt_random_items_with_fallback({}, "model", {}, contexts, "anima")

        self.assertEqual(calls, [2, 2, 1, 1])
        self.assertEqual(items, [{"index": 0, "tags": "tag 0"}, {"index": 1, "tags": "tag 1"}])
        self.assertTrue(strategy["fallback"])
        self.assertEqual(strategy["mode"], "single_fallback")

    def test_fallback_module_falls_back_to_single_item_calls_after_batch_failures(self) -> None:
        contexts = [{"index": 0, "existing_positive": ""}, {"index": 1, "existing_positive": ""}]
        calls: list[int] = []

        def fake_once(config, model, request_config, call_contexts, app_scope):
            calls.append(len(call_contexts))
            if len(call_contexts) > 1:
                raise ValueError("bad batch json")
            index = call_contexts[0]["index"]
            return [{"index": index, "tags": f"tag {index}"}]

        items, strategy = prompt_random_fallback._collect_prompt_random_items_with_fallback(
            {},
            "model",
            {},
            contexts,
            "anima",
            collect_once=fake_once,
        )

        self.assertEqual(calls, [2, 2, 1, 1])
        self.assertEqual(items, [{"index": 0, "tags": "tag 0"}, {"index": 1, "tags": "tag 1"}])
        self.assertTrue(strategy["fallback"])
        self.assertEqual(strategy["mode"], "single_fallback")

    def test_collect_items_uses_local_tags_when_single_item_calls_fail(self) -> None:
        contexts = [{"index": 0, "existing_positive": ""}, {"index": 1, "existing_positive": ""}]

        with mock.patch.object(prompt_random_collect, "_collect_prompt_random_items_once", side_effect=ValueError("bad json")):
            items, strategy = prompt_random_collect._collect_prompt_random_items_with_fallback({}, "model", {}, contexts, "anima")

        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["tags"] for item in items))
        self.assertTrue(strategy["fallback"])
        self.assertTrue(any("local fallback" in item for item in strategy["errors"]))

    def test_fallback_module_uses_local_tags_when_single_item_calls_fail(self) -> None:
        contexts = [{"index": 0, "existing_positive": ""}, {"index": 1, "existing_positive": ""}]

        items, strategy = prompt_random_fallback._collect_prompt_random_items_with_fallback(
            {},
            "model",
            {},
            contexts,
            "anima",
            collect_once=mock.Mock(side_effect=ValueError("bad json")),
        )

        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["tags"] for item in items))
        self.assertTrue(strategy["fallback"])
        self.assertTrue(any("local fallback" in item for item in strategy["errors"]))

    def test_service_collect_response_shape_preserves_generation_strategy(self) -> None:
        strategy = {"mode": "batch", "batch_attempts": 1, "fallback": False, "errors": []}

        with mock.patch.object(prompt_random_service, "ensure_provider_ready", return_value={"reachable": True, "models": ["qwen"]}), mock.patch.object(
            prompt_random_service,
            "_collect_prompt_random_items_with_fallback",
            return_value=([{"index": 0, "seed": 11, "tags": "red dress"}], strategy),
        ):
            result = prompt_random_service.collect_prompt_random_tags(
                {"prompt_converter": {"enabled": True, "provider": "lmstudio", "base_url": "http://127.0.0.1:1234/v1"}},
                feature={"enabled": True},
                contexts=[{"index": 0, "seed": 11, "existing_positive": ""}],
                app_scope="anima",
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["enabled"])
        self.assertEqual(result["generated_items"], [{"index": 0, "seed": 11, "tags": "red dress"}])
        self.assertEqual(result["generation_strategy"], strategy)
        self.assertEqual(result["provider"]["model"], "qwen")

    def test_attach_generated_item_to_each_request(self) -> None:
        requests = [{"queue_index": 0, "prompt_random_collect": {"enabled": True}}, {"queue_index": 1, "prompt_random_collect": {"enabled": True}}]
        prompt_random_collect.attach_prompt_random_collect_items(
            requests,
            {
                "instruction": "test",
                "mode": "positive_completion",
                "strength": "subtle",
                "include_characters": False,
                "use_character_motifs": True,
                "generated_items": [{"index": 0, "tags": "red dress"}, {"index": 1, "tags": "blue dress"}],
                "provider": {"model": "qwen"},
                "generation_strategy": {"mode": "batch", "batch_attempts": 1, "fallback": False, "errors": []},
            },
        )
        self.assertEqual(prompt_random_collect.prompt_random_collect_tags(requests[0]), "red dress")
        self.assertEqual(prompt_random_collect.prompt_random_collect_tags(requests[1]), "blue dress")
        self.assertEqual(requests[0]["prompt_random_collect"]["mode"], "positive_completion")
        self.assertFalse(requests[0]["prompt_random_collect"]["include_characters"])
        self.assertFalse(requests[0]["prompt_random_collect"]["use_character_motifs"])
        self.assertEqual(requests[0]["prompt_random_collect"]["generation_strategy"]["mode"], "batch")

    def test_history_summary_preserves_generated_tags_for_reuse_strip(self) -> None:
        summary = history_store._prompt_random_collect_summary(
            {
                "prompt_random_collect": {
                    "enabled": True,
                    "mode": "positive_completion",
                    "instruction": "test",
                    "strength": "subtle",
                    "include_characters": False,
                    "use_character_motifs": True,
                    "generated_item": {"index": 0, "tags": "red dress"},
                    "provider": {"model": "qwen"},
                    "generation_strategy": {"mode": "batch", "batch_attempts": 1, "fallback": False, "errors": []},
                }
            }
        )
        self.assertIsNotNone(summary)
        self.assertEqual(summary["mode"], "positive_completion")
        self.assertEqual(summary["generated_tags"], "red dress")
        self.assertFalse(summary["include_characters"])
        self.assertFalse(summary["use_character_motifs"])
        self.assertEqual(summary["generation_strategy"]["mode"], "batch")

    def test_history_summary_preserves_enabled_config_without_generated_tags(self) -> None:
        summary = history_store._prompt_random_collect_summary(
            {
                "prompt_random_collect": {
                    "enabled": True,
                    "instruction": "keep this",
                    "strength": "bold",
                    "include_characters": True,
                    "use_character_motifs": True,
                }
            }
        )
        self.assertIsNotNone(summary)
        self.assertTrue(summary["enabled"])
        self.assertEqual(summary["instruction"], "keep this")
        self.assertEqual(summary["strength"], "bold")
        self.assertTrue(summary["use_character_motifs"])
        self.assertEqual(summary["generated_tags"], "")

    def test_history_detail_enriches_raw_prompt_from_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload_path = Path(directory) / "payload.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "request": {
                            "positive_prompt": "raw positive",
                            "negative_prompt_raw": "raw negative",
                            "official_lora_preset": "fast_color",
                            "prompt_random_collect": {
                                "enabled": True,
                                "generated_tags": "blue dress",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            item = {"id": "test", "payload_path": str(payload_path), "positive": "masterpiece, raw positive, blue dress"}
            enriched = history_store.enrich_history_item_from_payload(item)
        self.assertEqual(enriched["positive_prompt"], "raw positive")
        self.assertEqual(enriched["negative_prompt_raw"], "raw negative")
        self.assertEqual(enriched["official_lora_preset"], "fast_color")
        self.assertEqual(enriched["prompt_random_collect"]["generated_tags"], "blue dress")


if __name__ == "__main__":
    unittest.main()
