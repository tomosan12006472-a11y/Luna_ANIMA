from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from . import comfy_client
from . import reference_store
from .config import COMFYUI_LORA_DIRS
from .generation_prepare import reference_modules_availability_payload
from .model_info_cache import _object_choice
from .payload_builder import compute_hires_size, resolve_official_loras
from .reference_modules import sanitize_reference_modules


LATENT_UPSCALE_METHODS = ["nearest-exact", "bilinear", "area", "bicubic", "bislerp", "lanczos"]
MAX_QUEUE_COUNT = 10
MAX_OUTPUT_PIXELS = 4096 * 4096


def _settings_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return value if isinstance(value, dict) else {}


def error_response(
    *,
    status_code: int,
    message: str,
    stage: str,
    data: Any | None = None,
    comfy_status: int | None = None,
    comfy_response_text: str = "",
    comfy_node_errors: Any = None,
    traceback_short: str = "",
    retryable: bool = False,
) -> JSONResponse:
    hires_fix = _settings_dict(data.hires_fix) if data else {}
    content = {
        "ok": False,
        "error_type": "generation_error",
        "stage": stage,
        "message": message,
        "mode": hires_fix.get("mode", ""),
        "workflow_mode": data.workflow_mode if data else "",
        "hires_fix": hires_fix,
        "comfy_status": comfy_status,
        "comfy_response_text": comfy_response_text,
        "comfy_node_errors": comfy_node_errors,
        "traceback_short": traceback_short,
        "retryable": retryable,
    }
    return JSONResponse(status_code=status_code, content=content)


def validate_hires_fix(data: Any, addr: str) -> JSONResponse | None:
    hires = _settings_dict(data.hires_fix)
    if not hires.get("enabled"):
        return None
    try:
        size = compute_hires_size(data.model_dump())
    except Exception as exc:
        return error_response(
            status_code=400,
            message=f"Invalid Hires.fix size: {exc}",
            stage="validate_hires_size",
            data=data,
            retryable=False,
        )
    if bool(hires.get("target_width")) != bool(hires.get("target_height")):
        return error_response(
            status_code=400,
            message="Hires.fix target width and height must be set together.",
            stage="validate_hires_size",
            data=data,
            comfy_node_errors=size,
            retryable=False,
        )
    if hires.get("target_width") and hires.get("target_height"):
        width_scale = size["final_width"] / data.width
        height_scale = size["final_height"] / data.height
        if abs(width_scale - height_scale) > 0.001:
            return error_response(
                status_code=400,
                message="Hires.fix target size must keep the same aspect ratio as the base resolution.",
                stage="validate_hires_size",
                data=data,
                comfy_node_errors={**size, "width_scale": width_scale, "height_scale": height_scale},
                retryable=False,
            )
    if not hires.get("target_width") and not hires.get("target_height") and float(hires.get("upscale_factor") or 0) <= 1.0:
        return error_response(
            status_code=400,
            message="Hires.fix factor must be greater than 1.0 when target size is not set.",
            stage="validate_hires_size",
            data=data,
            comfy_node_errors=size,
            retryable=False,
        )
    if size["final_width"] < data.width or size["final_height"] < data.height:
        return error_response(
            status_code=400,
            message="Hires.fix final size must be at least the base resolution.",
            stage="validate_hires_size",
            data=data,
            comfy_node_errors=size,
            retryable=False,
        )
    if int(size["final_width"]) * int(size["final_height"]) > MAX_OUTPUT_PIXELS:
        return error_response(
            status_code=400,
            message="Hires.fix final size is too large.",
            stage="validate_hires_size",
            data=data,
            comfy_node_errors={**size, "max_pixels": MAX_OUTPUT_PIXELS},
            retryable=False,
        )
    mode = str(hires.get("mode") or "latent")
    if mode == "latent":
        method = str(hires.get("latent_upscale_method") or hires.get("upscale_method") or "").strip()
        if method not in LATENT_UPSCALE_METHODS:
            return error_response(
                status_code=400,
                message="Hires.fix latent mode requires a valid latent upscale method.",
                stage="validate_hires_fix",
                data=data,
                comfy_node_errors={"received": method, "allowed": LATENT_UPSCALE_METHODS},
                retryable=False,
            )
        return None
    model_name = str(hires.get("upscale_model") or "").strip()
    if model_name.startswith("Latent"):
        return error_response(
            status_code=400,
            message="Hires.fix model mode requires a valid upscale model name.",
            stage="validate_hires_fix",
            data=data,
            comfy_node_errors={"received": model_name, "reason": "latent display label is not an upscale model"},
            retryable=False,
        )
    try:
        info = comfy_client.object_info(addr)
        allowed = _object_choice(info, "UpscaleModelLoader", "model_name")
    except Exception:
        allowed = []
    if allowed and model_name not in allowed:
        return error_response(
            status_code=400,
            message="Hires.fix model mode requires a valid upscale model name.",
            stage="validate_hires_fix",
            data=data,
            comfy_node_errors={"received": model_name, "allowed": allowed},
            retryable=False,
        )
    return None


def validate_image_to_image(data: Any) -> JSONResponse | None:
    i2i = _settings_dict(data.image_to_image)
    if not i2i.get("enabled"):
        return None
    if not str(i2i.get("image_id") or ""):
        return error_response(
            status_code=400,
            message="Image to Image is ON, but no i2i input image is selected.",
            stage="validate_i2i",
            data=data,
            comfy_node_errors={"missing": "image_to_image.image_id"},
            retryable=False,
        )
    hires = _settings_dict(data.hires_fix)
    if hires.get("enabled") and not i2i.get("allow_with_hires_fix"):
        return error_response(
            status_code=400,
            message="Image to Image + Hires.fix is disabled in this MVP. Turn Hires.fix off or enable the explicit override.",
            stage="validate_i2i",
            data=data,
            comfy_node_errors={"image_to_image": "hires_fix_not_allowed"},
            retryable=False,
        )
    reference = _settings_dict(data.reference_assist)
    if reference.get("enabled") and not i2i.get("allow_with_reference_assist"):
        return error_response(
            status_code=400,
            message="Image to Image + Reference Assist is disabled in this MVP. Turn Reference Assist off or enable the explicit override.",
            stage="validate_i2i",
            data=data,
            comfy_node_errors={"image_to_image": "reference_assist_not_allowed"},
            retryable=False,
        )
    return None


def validate_queue_count(data: Any) -> JSONResponse | None:
    if data.count < 1 or data.count > MAX_QUEUE_COUNT:
        return error_response(
            status_code=400,
            message=f"Generation count must be between 1 and {MAX_QUEUE_COUNT}.",
            stage="validate_queue_count",
            data=data,
            comfy_node_errors={"received": data.count, "allowed_min": 1, "allowed_max": MAX_QUEUE_COUNT},
            retryable=False,
        )
    return None


def validate_reference_modules(data: Any, addr: str) -> JSONResponse | None:
    modules = sanitize_reference_modules(_settings_dict(data.reference_modules), app_scope="anima")
    outfit = modules.get("outfit") if isinstance(modules.get("outfit"), dict) else {}
    caps = reference_modules_availability_payload(addr)
    if outfit.get("enabled"):
        if not outfit.get("image_id"):
            return error_response(
                status_code=400,
                message="Outfit固定がONですが、参照画像が選択されていません。参照画像を選ぶか、Outfit固定をOFFにしてください。",
                stage="validate_reference_modules",
                data=data,
                comfy_node_errors={"missing": "reference_modules.outfit.image_id"},
                retryable=False,
            )
        if not reference_store.get_reference_image(outfit["image_id"]):
            return error_response(
                status_code=400,
                message="Outfit固定の参照画像が見つかりません。参照画像を選び直すか、Outfit固定をOFFにしてください。",
                stage="validate_reference_modules",
                data=data,
                comfy_node_errors={"missing": "reference_modules.outfit.image"},
                retryable=False,
            )
        outfit_caps = (caps.get("reference_modules") or {}).get("outfit") or {}
        if not outfit_caps.get("available"):
            return error_response(
                status_code=400,
                message="Outfit固定に必要なIP-Adapter系ノードが見つかりません。Outfit固定をOFFにすると通常生成できます。",
                stage="validate_reference_modules",
                data=data,
                comfy_node_errors={"missing": outfit_caps.get("missing_nodes") or ["ip_adapter"], "warnings": outfit_caps.get("warnings") or []},
                retryable=False,
            )
    pose = modules.get("pose") if isinstance(modules.get("pose"), dict) else {}
    if pose.get("enabled"):
        if not pose.get("image_id"):
            return error_response(
                status_code=400,
                message="Pose固定がONですが、参照画像が選択されていません。参照画像を選ぶか、Pose固定をOFFにしてください。",
                stage="validate_reference_modules",
                data=data,
                comfy_node_errors={"missing": "reference_modules.pose.image_id"},
                retryable=False,
            )
        if not reference_store.get_reference_image(pose["image_id"]):
            return error_response(
                status_code=400,
                message="Pose固定の参照画像が見つかりません。参照画像を選び直すか、Pose固定をOFFにしてください。",
                stage="validate_reference_modules",
                data=data,
                comfy_node_errors={"missing": "reference_modules.pose.image"},
                retryable=False,
            )
        pose_caps = (caps.get("reference_modules") or {}).get("pose") or {}
        mode = str(pose.get("mode") or "pose_image")
        mode_caps = (pose_caps.get("modes") or {}).get(mode) or {}
        if not mode_caps.get("available"):
            return error_response(
                status_code=400,
                message="ANIMAのPose固定は、互換ControlNet経路が確認できるまで無効です。Pose固定をOFFにすると通常生成できます。",
                stage="validate_reference_modules",
                data=data,
                comfy_node_errors={"missing": mode_caps.get("missing_nodes") or pose_caps.get("missing_nodes") or ["pose_controlnet"], "warnings": pose_caps.get("warnings") or []},
                retryable=False,
            )
    background = modules.get("background") if isinstance(modules.get("background"), dict) else {}
    if background.get("enabled"):
        if not background.get("image_id"):
            return error_response(
                status_code=400,
                message="Background ReferenceがONですが、参照画像が選択されていません。参照画像を選ぶか、Background ReferenceをOFFにしてください。",
                stage="validate_reference_modules",
                data=data,
                comfy_node_errors={"missing": "reference_modules.background.image_id"},
                retryable=False,
            )
        if not reference_store.get_reference_image(background["image_id"]):
            return error_response(
                status_code=400,
                message="Background Referenceの参照画像が見つかりません。参照画像を選び直すか、Background ReferenceをOFFにしてください。",
                stage="validate_reference_modules",
                data=data,
                comfy_node_errors={"missing": "reference_modules.background.image"},
                retryable=False,
            )
    return None


def validate_official_loras(data: Any, addr: str) -> JSONResponse | None:
    resolved = resolve_official_loras(data.model_dump())
    enabled = [item for item in resolved.values() if item.get("enabled")]
    if not enabled:
        return None
    try:
        info = comfy_client.object_info(addr)
    except Exception as exc:
        return error_response(
            status_code=503,
            message=f"Could not check ComfyUI LoRA support: {exc}",
            stage="validate_official_loras",
            data=data,
            retryable=True,
        )
    if "LoraLoaderModelOnly" not in info:
        return error_response(
            status_code=400,
            message="LoraLoaderModelOnly is not available in ComfyUI.",
            stage="validate_official_loras",
            data=data,
            comfy_node_errors={"available_lora_loaders": sorted([name for name in info if "lora" in name.lower()])},
            retryable=False,
        )
    allowed = _object_choice(info, "LoraLoaderModelOnly", "lora_name")
    missing = [item["file"] for item in enabled if not item.get("path")]
    not_visible = [item["file"] for item in enabled if allowed and item["file"] not in allowed]
    if missing or not_visible:
        return error_response(
            status_code=400,
            message="Official ANIMA LoRA file is missing or not visible to ComfyUI.",
            stage="validate_official_loras",
            data=data,
            comfy_node_errors={
                "missing_files": missing,
                "not_visible_in_object_info": not_visible,
                "lora_dirs": [str(path) for path in COMFYUI_LORA_DIRS],
            },
            retryable=False,
        )
    return None
