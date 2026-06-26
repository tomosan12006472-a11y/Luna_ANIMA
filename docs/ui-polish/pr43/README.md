# PR43 Compact Generation Settings

## UX Measurement

Measured with Chrome/Playwright at `390x844` and `1440x1000`.

| State | scrollHeight | ratio | LoRA Y | Reference Y | Detailer Y | horizontal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Mobile before, tech open | 3483 | 4.13 | 2696 | 3169 | 3229 | no |
| Mobile after, output/model open | 2905 | 3.44 | 2309 | 2591 | 2651 | no |
| Desktop before, tech open | 3035 | 3.04 | 2364 | 2725 | 2785 | no |
| Desktop after, output/model open | 2672 | 2.67 | 2074 | 2362 | 2422 | no |

Closed mobile page height increased from `2209` to `2419` because the large technical fold was split into visible top-level groups. The tradeoff is intentional: users can reach Official LoRA, LoRA Slots, Quick Controls, Reference, and Detailer without opening one long technical tray.

## Information Architecture

- Kept the PR42 studio hero, primary Payload Preview, and sticky Generate flow.
- Split the previous technical tray into `Output / Model`, `ANIMA official LoRA`, `LoRA Slots`, `Quick Controls`, and `Confirm / Defaults`.
- Moved only low-frequency controls behind the new compact details; all existing inputs, IDs, and data-actions remain.
- Kept Quick Controls primary actions visible while moving per-feature bulk ON/OFF into a small nested fold.
- Left Reference, i2i, Hires.fix, and Detailers as top-level folds so their summaries remain scannable.

## Screenshots

### Mobile Top

Before:
![Mobile before top](before-mobile-top.png)

After:
![Mobile after top](after-mobile-top.png)

### Mobile Technical Settings

Before:
![Mobile before technical settings](before-mobile-tech-open.png)

After:
![Mobile after output model](after-mobile-tech-open.png)

### Mobile LoRA and Reference

![Mobile LoRA section](after-mobile-lora.png)

![Mobile Reference section](after-mobile-reference.png)

### Desktop

Before:
![Desktop before technical settings](before-desktop-tech-open.png)

After:
![Desktop after technical settings](after-desktop-tech-open.png)

### Sheets

History thumbnails are blurred for review safety.

![History sheet](after-mobile-history-blurred.png)

![Settings sheet](after-mobile-settings.png)
