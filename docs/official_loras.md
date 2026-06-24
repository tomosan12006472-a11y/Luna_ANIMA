# Official ANIMA LoRAs

Luna ANIMA can apply a small set of optional official LoRAs from the generation UI. The model files are not bundled with this repository.

## Presets

The `ANIMA公式LoRA` section includes built-in presets for Highres, Turbo, and ColorFix combinations:

- `OFF`
- `Color Stable`
- `Quality`
- `Fast Preview`
- `Fast Color`
- `Final Quality`

Applying a preset updates the existing individual controls. You can still fine-tune Highres, Turbo, and ColorFix manually after applying a preset. Turbo presets keep the existing recommended steps/cfg/strength behavior.

## ColorFix

ColorFix is an optional ANIMA LoRA for color tone, saturation, and color stability adjustments.

- Source model page: <https://civitai.com/models/2435207/anima-colorfix>
- The current default targets the v1.0 file `Anima_colorfix_v1_by_Volnovik.safetensors`.
- Download the LoRA file from your chosen source and place it in a ComfyUI LoRA directory.
- The default configured filename is `anima\Anima_colorfix_v1_by_Volnovik.safetensors`.
- If your local filename or subfolder differs, set `ANIMA_COLORFIX_LORA_NAME` before launching Luna ANIMA.
- Enable it with the `ColorFix` checkbox under `ANIMA公式LoRA`.
- The default strength is `0.6`.
- The model page notes it is designed around weight `1`; use the UI strength control to adjust per image and LoRA stack.
- If ComfyUI cannot see the configured file, generation validation and diagnostics report the missing official LoRA.

Example:

```bat
set ANIMA_COLORFIX_LORA_NAME=anima\Anima_colorfix_v1_by_Volnovik.safetensors
run_luna_anima.bat
```
