# Third-Party Notices

Luna ANIMA is a local UI package that works with external software and data.

## Runtime Dependencies

- Python
- FastAPI
- Uvicorn
- Pillow
- ComfyUI

Install third-party Python packages from `requirements.txt`. Each dependency is distributed under its own license.

## External Generation Environment

Image generation requires a local ComfyUI installation and compatible model files, LoRA files, and custom nodes. These are not included in this package.

## Character Catalog Data

The bundled character catalog is derived from compatible character tag datasets and Japanese display-name mapping data that were reviewed before import. The catalog is included to make Luna ANIMA usable without a separate external character-select app.

## Optional Local LLM Providers

Prompt conversion and Prompt Random Collect can use OpenAI-compatible local endpoints from LM Studio, Ollama, or llama.cpp. These providers and models are not included in this package.
