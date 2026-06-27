# Luna ANIMA

Luna ANIMA is a local darkroom UI for ANIMA-style image generation through ComfyUI.

## What You Need

- Windows 10/11
- Python 3.11 or newer
- ComfyUI running locally
- Required ANIMA image model files and ComfyUI custom nodes installed in your ComfyUI environment
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

- `1234`

To change the PIN:

```bat
set LUNA_ANIMA_PIN=1234
run_luna_anima.bat
```

By default Luna ANIMA binds to `127.0.0.1`. To expose the app on another host:

```bat
set LUNA_ANIMA_HOST=0.0.0.0
set LUNA_ANIMA_PIN=your-private-pin
run_luna_anima.bat
```

Startup is refused when `LUNA_ANIMA_HOST` is `0.0.0.0` or `::` and the default PIN is still in use.

## Runtime Layout

- `app/main.py` builds the FastAPI app, installs middleware, mounts static assets, runs the startup security check, and includes routers.
- API routes live under `app/api/`.
- Request models live under `app/schemas/`.
- Session authentication lives in `app/auth.py`; the cookie name is `anima_claude_session`.
- Shared static/file response helpers live in `app/responses.py`.
- ComfyUI payload generation remains in `app/payload_builder.py`.

## Development Checks

Use Python 3.11 or newer. Local setup can be created with `setup_venv.bat`.

```bat
node scripts/check_frontend_js.mjs
node scripts/check_static_import_tokens.mjs
node scripts/check_frontend_contracts.mjs
python -m unittest discover -s tests
python -m compileall app tests
git diff --check
```

The CI test suite does not require ComfyUI, LM Studio, Ollama, or llama.cpp to be running.

Frontend modules live under `app/static/js`. `app/static/app.js` is a compatibility bootstrap, while `app/static/js/main.js` should stay focused on app shell wiring, shared feature context, action registration, and startup orchestration. The frontend checks cover JavaScript syntax, static import cache tokens, and lightweight contracts for factory exports, actions, API paths, request keys, and key DOM/state references.

After the PR that adds the frontend contract check is merged green, the large structural refactoring is considered complete. Future work should be treated as feature improvement, observability, regression hardening, or bugfix work. Further module splits should stay small and needs-driven.

See `docs/frontend_modules.md` for the current frontend module map and maintenance boundaries.
See `docs/background_reference.md` for Background Reference v1 setup notes, expected ComfyUI nodes, and current limitations.
See `docs/official_loras.md` for optional official ANIMA LoRA setup, including ColorFix.
See `docs/reference_setup.md` for IPAdapter / ControlNet / ControlNet Aux setup checks for Reference Modules.
See `docs/mobile_operations.md` for mobile ComfyUI restart control and async public-save behavior.
See `docs/public_save_finish.md` for optional public-save finish presets and transparent signature-image watermarks.

## Notes

- Generated images, history, recipes, favorites, uploaded references, and settings are stored under `user_data`.
- `user_data` is intentionally not included in distribution packages.
- Existing `user_data/settings.json` and saved history are expected to remain compatible across refactors.
- The character catalog is bundled under `config`. A legacy external catalog can still be used with `LUNA_CHARACTER_CATALOG_ROOT`.
- Model files, LoRA files, LoRA trigger-word catalogs, and personal Original character presets are not included.
- Personal positive prompt templates are not included; distribution packages start with an empty template catalog.
- LoRA controls only scan and use files already installed in the user's local ComfyUI environment.
- ComfyUI API defaults to `127.0.0.1:8188`. Override it with `COMFYUI_ADDR`.
- Reference and image-to-image uploads use FastAPI multipart upload handling.
- Redistribution and program modification are prohibited. See `LUNA_DISTRIBUTION_TERMS.md`.
