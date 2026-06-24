from __future__ import annotations

from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parents[1]
USER_DATA_DIR = ROOT_DIR / "user_data"
PAYLOAD_DIR = USER_DATA_DIR / "payloads"
MOBILE_PAYLOAD_DIR = PAYLOAD_DIR
DIFF_REPORT_DIR = USER_DATA_DIR / "diff_reports"
HISTORY_DIR = USER_DATA_DIR / "history"
IMAGE_DIR = USER_DATA_DIR / "images"
THUMBNAIL_DIR = USER_DATA_DIR / "thumbnails"
PUBLIC_DIR = USER_DATA_DIR / "public"
SETTINGS_PATH = USER_DATA_DIR / "settings.json"
FAVORITES_PATH = USER_DATA_DIR / "favorites.json"

CHARACTER_CATALOG_ROOT = Path(os.environ.get("LUNA_CHARACTER_CATALOG_ROOT", str(ROOT_DIR / "config")))
CHARACTER_CATALOG_WAI_PATH = ROOT_DIR / "config" / "wai_characters.csv"
CHARACTER_CATALOG_ORIGINAL_PATH = ROOT_DIR / "config" / "original_character.json"
COMFYUI_ADDR_DEFAULT = os.environ.get("COMFYUI_ADDR", "127.0.0.1:8188")
APP_PIN_DEFAULT = "1234"
APP_PIN = os.environ.get("LUNA_ANIMA_PIN", os.environ.get("ANIMA_CLAUDE_PIN", APP_PIN_DEFAULT))
LUNA_ANIMA_HOST = os.environ.get("LUNA_ANIMA_HOST", "127.0.0.1")
ANIMA_WORKFLOW_PATH = ROOT_DIR / "config" / "workflows" / "anima_base_api.json"
ANIMA_MAPPING_PATH = ROOT_DIR / "config" / "anima_mapping.json"
COMFYUI_LORA_DIRS = [
    Path(os.environ.get("COMFYUI_LORA_DIR", r"D:\AI\ComfyUI\models\loras")),
    Path(os.environ.get("COMFYUI_PORTABLE_LORA_DIR", r"D:\AI\ComfyUI\ComfyUI\models\loras")),
]
ANIMA_HIGHRES_LORA_NAME = "anima-highres-aesthetic-boost.safetensors"
ANIMA_TURBO_LORA_V02_NAME = "anima-turbo-lora-v0.2.safetensors"
ANIMA_TURBO_LORA_V01_NAME = "anima-turbo-lora-v0.1.safetensors"
ANIMA_COLORFIX_LORA_NAME = os.environ.get("ANIMA_COLORFIX_LORA_NAME", r"anima\Anima_colorfix_v1_by_Volnovik.safetensors")
COMFYUI_ANIMA_TEMPLATE_PATH = Path(os.environ.get("COMFYUI_ANIMA_TEMPLATE_PATH", r"D:\AI\ComfyUI\ComfyUI\user\default\workflows\Anima_テンプレ.json"))

for path in (
    USER_DATA_DIR,
    PAYLOAD_DIR,
    DIFF_REPORT_DIR,
    HISTORY_DIR,
    IMAGE_DIR,
    THUMBNAIL_DIR,
    PUBLIC_DIR,
):
    path.mkdir(parents=True, exist_ok=True)


def validate_startup_security() -> None:
    host = str(LUNA_ANIMA_HOST or "127.0.0.1").strip()
    if host in {"0.0.0.0", "::"} and APP_PIN == APP_PIN_DEFAULT:
        raise RuntimeError(
            "Refusing to start Luna ANIMA on a public host with the default PIN. "
            "Set LUNA_ANIMA_PIN to a non-default value or use LUNA_ANIMA_HOST=127.0.0.1."
        )
