# ANIMA Claude

ANIMA Claude is a separate darkroom-style FastAPI app for driving the existing ANIMA workflow without replacing ANIMA_MobilePanel. It runs on port `51031`, so it can run alongside the original ANIMA_MobilePanel service.

## Setup

```bat
cd /d D:\AI\ANIMA_claude
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Launch

```bat
run_anima_claude.bat
```

Open `http://127.0.0.1:51031/`.

## Auth

The default PIN is `2197`.

To override it:

```bat
set ANIMA_CLAUDE_PIN=1234
run_anima_claude.bat
```

The session cookie name is `anima_claude_session`.

## References

- Character catalog source: SAA CSV under `SAA_ROOT`.
- ComfyUI API: `127.0.0.1:8188` by default via `COMFYUI_ADDR`.
- ANIMA workflow: `config/workflows/anima_base_api.json`.
- ANIMA mapping: `config/anima_mapping.json`.
