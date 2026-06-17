# Luna ANIMA

Luna ANIMA is a local darkroom UI for ANIMA-style image generation through ComfyUI.

## What You Need

- Windows 10/11
- Python 3.11 or newer
- ComfyUI running locally
- Required ANIMA/Qwen model files and ComfyUI custom nodes installed in your ComfyUI environment
- Optional: LM Studio, Ollama, or llama.cpp for Japanese-to-English prompt conversion and Prompt Random Collect

## Setup

```bat
cd /d path\to\Luna_ANIMA
setup_venv.bat
```

## Launch

```bat
run_luna_anima.bat
```

Open:

- http://127.0.0.1:51031/

Default PIN:

- `2197`

To change the PIN:

```bat
set LUNA_ANIMA_PIN=1234
run_luna_anima.bat
```

## Notes

- Generated images, history, recipes, favorites, uploaded references, and settings are stored under `user_data`.
- `user_data` is intentionally not included in distribution packages.
- The character catalog is bundled under `config`. A legacy external catalog can still be used with `LUNA_CHARACTER_CATALOG_ROOT`.
- Model files, LoRA files, LoRA trigger-word catalogs, and personal Original character presets are not included.
- Personal positive prompt templates are not included; distribution packages start with an empty template catalog.
- LoRA controls only scan and use files already installed in the user's local ComfyUI environment.
- ComfyUI API defaults to `127.0.0.1:8188`. Override it with `COMFYUI_ADDR`.
- Redistribution and program modification are prohibited. See `LUNA_DISTRIBUTION_TERMS.md`.
