# Public Save Finish and Signature Images

Luna ANIMA can optionally apply a small Pillow-based finish step when a history image is saved for public sharing. This is intended to mirror a local Krita "itsumono" finish without launching Krita, G'MIC, or any external GUI during save.

## Krita "itsumono" Finish

The committed default is a no-op. If no local preset exists, public-save behavior remains unchanged.

To enable a local preset:

1. Copy `config/krita_itsumono.example.json` to `user_data/public_save_finish/krita_itsumono.json`.
2. Replace `operations` with your real local finish values.
3. Open Settings and enable `Krita「いつもの」仕上げ`.

Supported operation types are intentionally small and Pillow-only:

- `brightness_contrast` with `brightness` from `-1.0` to `1.0` and `contrast` as a factor.
- `saturation` or `color` with `factor`.
- `gamma` with `gamma`.
- `sharpness` with `factor`.
- `krita_perchannel` with Krita `perchannel` curve strings. For current Krita RGB/RGBA presets, curve order is `curve0` all colors, `curve1` red, `curve2` green, `curve3` blue, `curve4` alpha, `curve5` hue, `curve6` saturation, and `curve7` lightness. Luna ANIMA applies the all-colors and RGB curves and leaves alpha/hue/saturation/lightness untouched unless they are identity curves.

Example `krita_perchannel` operation:

```json
{
  "type": "krita_perchannel",
  "n_transfers": 8,
  "curves": {
    "curve0": "0,0;1,1;",
    "curve1": "0,0;0.25098,0.215686;0.74902,0.788235;1,1;",
    "curve2": "0,0;1,1;",
    "curve3": "0,0;0.25098,0.290196;0.74902,0.709804;1,1;",
    "curve4": "0,0;1,1;",
    "curve5": "0,0;1,1;",
    "curve6": "0,0;1,1;",
    "curve7": "0,0;1,1;"
  }
}
```

The save pipeline is:

1. Source history image
2. Optional public-save finish
3. Optional text watermark or signature image
4. Public image output

You can also point to a preset with:

- `LUNA_KRITA_ITSUMONO_PRESET`
- `LUNA_PUBLIC_SAVE_FINISH_PRESET`

The repository does not include personal Krita presets or inferred finish numbers.

## Signature Image Watermark

Settings supports a `サイン画像` watermark mode. Uploaded signature images are validated with Pillow and stored under `user_data/signatures/`.

The API does not expose full local paths. Public save metadata stores only the selected signature id, scale, position, opacity, and cache hash inputs.

Recommended use:

1. Prepare a transparent PNG signature.
2. Upload it from Settings.
3. Select `サイン画像` as the watermark mode.
4. Adjust scale, opacity, and position.

Signature images are applied with alpha compositing. They are not stored in browser localStorage or IndexedDB.
