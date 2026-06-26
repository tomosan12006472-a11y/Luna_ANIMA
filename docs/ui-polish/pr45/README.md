# PR45 frequency workbench layout

## Goal

Reorganize the generation screen by usage frequency instead of feature category.
The main path is now:

- Character
- Prompt Workbench
- Tuning Workbench
- Advanced Assist
- Confirm / Defaults

Prompt conversion, Prompt Random, Official LoRA, LoRA slots, Hires.fix, and Quick Controls are reachable from the two open workbenches. Reference, i2i, Detailers, and Dynamic Prompt move under Advanced Assist with a compact status summary.

## Metrics

Measured with a fresh authenticated browser context.

| Metric | PR44 mobile 390x844 | PR45 mobile 390x844 | PR44 desktop 1440x1000 | PR45 desktop 1440x1000 |
| --- | ---: | ---: | ---: | ---: |
| scrollHeight | 2311 | 2068 | 2081 | 1786 |
| clientHeight | 844 | 844 | 1000 | 1000 |
| ratio | 2.74 | 2.45 | 2.08 | 1.79 |
| top-level details | 8 | 4 | 8 | 4 |
| horizontal scroll | no | no | no | no |

## Reachability

| Target | PR44 mobile Y | PR45 mobile Y | Change |
| --- | ---: | ---: | ---: |
| Prompt area / Workbench | 1178 | 953 | -225 |
| Prompt Converter | 1332 | 1008 | -324 |
| Prompt Random | 1392 | 1008 | -384 |
| LoRA Slots tab | 1769 | 1472 | -297 |
| Hires.fix tab | 1877 | 1472 | -405 |
| Reference tab | 1997 | 1861 | -136 |
| Detailer tab | 2057 | 1861 | -196 |

## Structure Changes

- Prompt-related controls are grouped under `Prompt Workbench` with Write / Convert / Random / More tabs.
- Official LoRA, LoRA slots, Hires.fix, Quick Controls, and Output/Model are grouped under `Tuning Workbench`.
- Tuning opens on Official by default so LoRA/Hires/Quick stay near the top; Output/Model remains available as the last tab.
- i2i, Reference Modules, Face/Hand Detailer, and Dynamic Prompt are grouped under `Advanced Assist`.
- Existing DOM IDs and data-action names are preserved.
- Fold keys changed for the compact layout: older `tech`, `assist-hub`, `hires`, `i2i`, `refmod`, `facedetailer`, `handdetailer`, and `dynamic` preferences are safely ignored by the new workbench structure.

## Screenshots

- [Before mobile top](before-mobile-top.png)
- [After mobile top](after-mobile-top.png)
- [Prompt Convert](after-mobile-prompt-convert.png)
- [Prompt Random](after-mobile-prompt-random.png)
- [Tuning Official](after-mobile-tuning-official.png)
- [Tuning LoRA](after-mobile-tuning-lora.png)
- [Tuning Hires](after-mobile-tuning-hires.png)
- [Advanced Reference](after-mobile-advanced-reference.png)
- [Advanced Finish](after-mobile-advanced-finish.png)
- [Desktop generation settings](after-desktop-generation-settings.png)
- [History view blurred](after-desktop-history-view-blurred.png)
- [Settings view](after-desktop-settings-view.png)

## Follow-up

- Advanced Assist is now compact, but Reference/Detailer contents are still dense once opened.
- Output/Model is intentionally lower priority than LoRA/Hires for this phase; if size/model edits become a more frequent mobile task, a small quick row can be added later without changing payload shape.
