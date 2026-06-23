from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .config import ANIMA_MAPPING_PATH
from .schemas.reference import BACKGROUND_REFERENCE_MODE_DEFAULTS, ReferenceModulesSettings


DEFAULT_REFERENCE_MODULES: dict[str, Any] = {
    "enabled": True,
    "preset": "off",
    "outfit": {
        "enabled": False,
        "image_id": "",
        "image_name": "",
        "strength": 0.45,
        "mode": "image_prompt",
        "strategy": "ip_adapter",
        "crop_mode": "user_prepared",
        "start_at": 0.0,
        "end_at": 0.75,
        "preset": "REGULAR - FLUX and SD3.5 only (high strength)",
        "provider": "CUDA",
    },
    "pose": {
        "enabled": False,
        "image_id": "",
        "image_name": "",
        "mode": "pose_image",
        "strength": 0.75,
        "start_at": 0.0,
        "end_at": 0.85,
        "strategy": "controlnet_openpose",
        "controlnet_model": "",
        "union_type": "openpose",
        "comfyui_image": {"name": None, "subfolder": "", "type": "input"},
    },
    "background": {
        "enabled": False,
        "image_id": "",
        "image_name": "",
        "mode": "depth",
        "strength": 0.45,
        "start_at": 0.0,
        "end_at": 0.75,
        "resize_mode": "crop",
        "strategy": "controlnet_background",
        "controlnet_model": "auto",
        "preprocessor_node_class": "",
        "apply_node_class": "ControlNetApplyAdvanced",
        "loader_node_class": "ControlNetLoader",
        "image_resize_node_class": "ImageScale",
        "comfyui_image": {"name": None, "subfolder": "", "type": "input"},
    },
}

REFERENCE_MODULE_NAMES = {"outfit", "pose", "background"}


def clamp_float(value: Any, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def sanitize_reference_modules(value: Any, *, app_scope: str = "anima") -> dict[str, Any]:
    raw = value.model_dump() if hasattr(value, "model_dump") else value if isinstance(value, dict) else {}
    data = ReferenceModulesSettings.model_validate(raw).model_dump()
    if app_scope != "anima":
        outfit = data.get("outfit") if isinstance(data.get("outfit"), dict) else {}
        if outfit.get("preset") == "REGULAR - FLUX and SD3.5 only (high strength)":
            outfit["preset"] = "PLUS (high strength)"
            data["outfit"] = outfit
    return data


def _input_choices(info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    spec = info.get(class_name, {}).get("input", {}).get("required", {}).get(input_name)
    if isinstance(spec, list) and spec and isinstance(spec[0], list):
        return [str(item) for item in spec[0]]
    return []


def _is_lllite_model(name: str) -> bool:
    return "lllite" in str(name or "").lower()


def _controlnet_choices(info: dict[str, Any]) -> list[str]:
    return _input_choices(info, "ControlNetLoader", "control_net_name")


def _regular_controlnet_choices(info: dict[str, Any]) -> list[str]:
    return [model for model in _controlnet_choices(info) if not _is_lllite_model(model)]


def _lllite_choices(info: dict[str, Any]) -> list[str]:
    choices = _input_choices(info, "AnimaLLLiteApply", "lllite_name")
    if choices:
        return [model for model in choices if _is_lllite_model(model)]
    return [model for model in _controlnet_choices(info) if _is_lllite_model(model)]


def _anima_lllite_capability(info: dict[str, Any], *, app_scope: str) -> dict[str, Any]:
    choices = _lllite_choices(info)
    has_node = "AnimaLLLiteApply" in info
    node = info.get("AnimaLLLiteApply") if isinstance(info.get("AnimaLLLiteApply"), dict) else {}
    optional = ((node.get("input") or {}).get("optional") or {}) if isinstance(node, dict) else {}
    inpainting_model = next((model for model in choices if "inpainting-v2" in model.lower()), "")
    regional_model = next((model for model in choices if "regional" in model.lower()), "")
    warnings: list[str] = []
    if app_scope != "anima":
        warnings.append("Anima LLLite is only intended for Luna ANIMA workflows.")
    if not has_node:
        warnings.append("ComfyUI-Anima-LLLite node is not available.")
    if not inpainting_model:
        warnings.append("anima-lllite-inpainting-v2.safetensors is not available.")
    if not regional_model:
        warnings.append("anima-lllite-regional-exp-v3.safetensors is not available.")
    return {
        "implemented": app_scope == "anima",
        "available": app_scope == "anima" and has_node and bool(inpainting_model or regional_model),
        "strategy": "anima_lllite",
        "apply_node": "AnimaLLLiteApply" if has_node else "",
        "models": choices,
        "inpainting_model": inpainting_model,
        "regional_model": regional_model,
        "mask_supported": "mask" in optional,
        "warnings": warnings,
    }


POSE_PREPROCESSOR_NODES = (
    "DWPreprocessor",
    "DWPose_Preprocessor",
    "OpenposePreprocessor",
    "OpenPosePreprocessor",
    "AIO Aux Preprocessor",
)


def _select_pose_controlnet_model(models: list[str]) -> tuple[str, bool]:
    for model in models:
        lower = model.lower()
        if "openpose" in lower or "dwpose" in lower or ("pose" in lower and "tile" not in lower):
            return model, False
    for model in models:
        if "union" in model.lower():
            return model, True
    return "", False


BACKGROUND_PREPROCESSOR_NODES: dict[str, tuple[str, ...]] = {
    "depth": (
        "DepthAnythingV2Preprocessor",
        "DepthAnythingPreprocessor",
        "MiDaS-DepthMapPreprocessor",
        "Zoe-DepthMapPreprocessor",
        "LeReS-DepthMapPreprocessor",
    ),
    "canny": ("CannyEdgePreprocessor", "CannyPreprocessor", "Canny"),
    "lineart": ("LineArtPreprocessor", "LineartPreprocessor", "LineArt_Preprocessor"),
    "softedge": ("HEDPreprocessor", "SoftEdgePreprocessor", "HEDPreprocessor_safe"),
    "mlsd": ("MLSDPreprocessor", "M-LSDPreprocessor", "M-LSDPreprocessor Provider"),
}

BACKGROUND_MODEL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "depth": ("depth", "zoe", "midas"),
    "canny": ("canny",),
    "lineart": ("lineart", "line"),
    "softedge": ("softedge", "hed", "scribble"),
    "mlsd": ("mlsd", "m-lsd"),
}


def _background_reference_mapping() -> dict[str, Any]:
    try:
        mapping = json.loads(ANIMA_MAPPING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    background = mapping.get("background_reference") if isinstance(mapping, dict) else {}
    return background if isinstance(background, dict) else {}


def _background_mode_mapping(mapping: dict[str, Any], mode: str) -> dict[str, Any]:
    modes = mapping.get("modes") if isinstance(mapping.get("modes"), dict) else {}
    value = modes.get(mode) if isinstance(modes.get(mode), dict) else {}
    return value


def _node_input_sections(info: dict[str, Any], class_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    node = info.get(class_name) if isinstance(info.get(class_name), dict) else {}
    inputs = node.get("input") if isinstance(node.get("input"), dict) else {}
    required = inputs.get("required") if isinstance(inputs.get("required"), dict) else {}
    optional = inputs.get("optional") if isinstance(inputs.get("optional"), dict) else {}
    return required, optional


def _default_preprocessor_value(name: str, mode: str) -> Any:
    if name == "image":
        return "__image__"
    if name in {"resolution", "detect_resolution", "image_resolution"}:
        return 1024
    if name == "safe":
        return "enable"
    if name == "low_threshold":
        return 100
    if name == "high_threshold":
        return 200
    if name in {"score_threshold", "thr_v"}:
        return 0.1
    if name in {"dist_threshold", "thr_d"}:
        return 0.1
    if name in {"mode", "preprocessor"}:
        return mode
    return None


def _preprocessor_input_defaults(info: dict[str, Any], class_name: str, mode: str, configured: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    required, optional = _node_input_sections(info, class_name)
    names = [*required.keys(), *optional.keys()]
    defaults = dict(configured or {})
    for name in names:
        if name in defaults:
            continue
        default = _default_preprocessor_value(name, mode)
        if default is not None:
            defaults[name] = default
    missing_required = [name for name in required if name not in defaults]
    return defaults, missing_required


def _select_background_model(models: list[str], mode: str, configured: str) -> tuple[str, list[str]]:
    configured = str(configured or "").strip()
    if configured and configured.lower() != "auto":
        missing = ["background_controlnet_model"] if models and configured not in models else []
        return configured, missing
    keywords = BACKGROUND_MODEL_KEYWORDS.get(mode, ())
    for model in models:
        lower = model.lower()
        if any(keyword in lower for keyword in keywords):
            return model, []
    return "", ["compatible_background_controlnet_model"]


def _background_capability(info: dict[str, Any], *, app_scope: str) -> dict[str, Any]:
    node_names = set(info.keys())
    mapping = _background_reference_mapping()
    mapping_enabled = bool(mapping.get("enabled"))
    loader_node = str(mapping.get("loader_node_class") or "ControlNetLoader")
    apply_node = str(mapping.get("apply_node_class") or "ControlNetApplyAdvanced")
    resize_node = str(mapping.get("image_resize_node_class") or "")
    models = _regular_controlnet_choices(info)
    warnings: list[str] = []
    if not mapping_enabled:
        warnings.append("background_reference mapping is not configured or disabled.")
    required = ["LoadImage", loader_node, apply_node]
    if resize_node:
        required.append(resize_node)
    missing_base = [name for name in required if name and name not in node_names]
    modes: dict[str, Any] = {}
    for mode in BACKGROUND_REFERENCE_MODE_DEFAULTS:
        mode_mapping = _background_mode_mapping(mapping, mode)
        configured_preprocessor = str(mode_mapping.get("preprocessor_node_class") or "").strip()
        preprocessor = ""
        if configured_preprocessor and configured_preprocessor in node_names:
            preprocessor = configured_preprocessor
        elif configured_preprocessor:
            preprocessor = configured_preprocessor
        else:
            preprocessor = next((name for name in BACKGROUND_PREPROCESSOR_NODES.get(mode, ()) if name in node_names), "")
        configured_inputs = mode_mapping.get("preprocessor_inputs") if isinstance(mode_mapping.get("preprocessor_inputs"), dict) else {}
        preprocessor_inputs, missing_inputs = _preprocessor_input_defaults(info, preprocessor, mode, configured_inputs) if preprocessor in node_names else ({}, [])
        model, missing_model = _select_background_model(models, mode, str(mode_mapping.get("controlnet_model") or "auto"))
        missing = [*missing_base]
        if not preprocessor or preprocessor not in node_names:
            missing.append("background_preprocessor")
        missing.extend(missing_inputs)
        missing.extend(missing_model)
        modes[mode] = {
            "available": bool(mapping_enabled and not missing),
            "preprocessor_node_class": preprocessor,
            "preprocessor_inputs": preprocessor_inputs,
            "controlnet_model": model,
            "missing_nodes": missing,
            "defaults": BACKGROUND_REFERENCE_MODE_DEFAULTS[mode],
        }
    available_modes = [mode for mode, data in modes.items() if data.get("available")]
    if app_scope != "anima":
        warnings.append("Background Reference v1 is tuned for Luna ANIMA workflows.")
    if not models:
        warnings.append("No regular ControlNet models were found.")
    return {
        "implemented": True,
        "available": bool(available_modes),
        "strategy": "controlnet_background",
        "modes": modes,
        "supported_modes": available_modes,
        "apply_node": apply_node if apply_node in node_names else "",
        "loader_node": loader_node if loader_node in node_names else "",
        "image_resize_node": resize_node if resize_node in node_names else "",
        "controlnet_models": models,
        "required_nodes": required,
        "missing_nodes": sorted({item for mode in modes.values() for item in mode.get("missing_nodes", [])}),
        "warnings": warnings,
    }


def _pose_capability(info: dict[str, Any], *, app_scope: str) -> dict[str, Any]:
    node_names = set(info.keys())
    models = _regular_controlnet_choices(info)
    selected_model, needs_union_type = _select_pose_controlnet_model(models)
    apply_node = "ControlNetApplyAdvanced" if "ControlNetApplyAdvanced" in node_names else ""
    preprocessor = next((name for name in POSE_PREPROCESSOR_NODES if name in node_names), "")
    required = ["LoadImage", "ControlNetLoader", "ControlNetApplyAdvanced"]
    missing = [name for name in required if name not in node_names]
    if not selected_model:
        missing.append("compatible_openpose_controlnet_model")
    if needs_union_type and "SetUnionControlNetType" not in node_names:
        missing.append("SetUnionControlNetType")
    pose_image_available = app_scope == "saa" and not missing
    auto_available = pose_image_available and bool(preprocessor)
    warnings: list[str] = []
    if app_scope == "anima":
        warnings.append("ANIMA Pose reference is disabled until a compatible image-model ControlNet route is confirmed.")
    if not preprocessor:
        warnings.append("DWPose/OpenPose preprocessor is not available; use a prepared OpenPose-style pose image.")
    if not selected_model:
        warnings.append("No compatible OpenPose/Union ControlNet model was found.")
    return {
        "implemented": True,
        "available": bool(pose_image_available or auto_available),
        "strategy": "controlnet_openpose",
        "apply_node": apply_node,
        "controlnet_model": selected_model,
        "controlnet_models": models,
        "requires_union_type": bool(needs_union_type),
        "union_type": "openpose" if needs_union_type else "",
        "preprocessor": preprocessor,
        "modes": {
            "pose_image": {"available": bool(pose_image_available), "missing_nodes": missing},
            "auto_dwpose": {"available": bool(auto_available), "missing_nodes": missing + ([] if preprocessor else ["dwpose_or_openpose_preprocessor"])},
        },
        "required_nodes": required,
        "missing_nodes": missing,
        "available_nodes": [name for name in [*required, "SetUnionControlNetType", *POSE_PREPROCESSOR_NODES] if name in node_names],
        "warnings": warnings,
    }


def reference_module_capabilities(info: dict[str, Any] | None, *, cache: dict[str, Any] | None = None, app_scope: str = "anima") -> dict[str, Any]:
    info = info or {}
    node_names = set(info.keys())
    node = "easy ipadapterApply" if "easy ipadapterApply" in node_names else ""
    required = ["LoadImage"]
    if not node:
        required.append("easy ipadapterApply")
    presets = _input_choices(info, node, "preset") if node else []
    providers = _input_choices(info, node, "provider") if node else []
    default_preset = "REGULAR - FLUX and SD3.5 only (high strength)" if app_scope == "anima" else "PLUS (high strength)"
    warnings: list[str] = []
    if not node:
        warnings.append("Outfit reference module requires an IP-Adapter apply node such as easy ipadapterApply.")
    if "LoadImage" not in node_names:
        warnings.append("Outfit reference module requires LoadImage.")
    if presets and default_preset not in presets:
        warnings.append(f"Preferred IP-Adapter preset is not available: {default_preset}")
    if app_scope == "anima":
        warnings.append("ANIMA outfit reference uses a generic IP-Adapter node; image-model compatibility depends on the local ComfyUI setup.")
    pose_capability = _pose_capability(info, app_scope=app_scope)
    background_capability = _background_capability(info, app_scope=app_scope)
    return {
        "reference_modules": {
            "outfit": {
                "implemented": True,
                "available": bool(node and "LoadImage" in node_names),
                "strategy": "ip_adapter",
                "apply_node": node,
                "required_nodes": required,
                "missing_nodes": [name for name in required if name not in node_names],
                "presets": presets,
                "providers": providers,
                "default_preset": default_preset,
                "warnings": warnings,
                "cache": cache or {},
            },
            "pose": pose_capability,
            "background": background_capability,
            "anima_lllite": _anima_lllite_capability(info, app_scope=app_scope),
            "character": {"implemented": False, "available": False, "strategy": "future", "warnings": ["Character module is not implemented in this MVP."]},
            "composition": {"implemented": False, "available": False, "strategy": "future", "warnings": ["Composition module is not implemented in this MVP."]},
        }
    }


def _scan_model_dir(path: Path, suffixes: tuple[str, ...] = (".safetensors", ".bin", ".pt", ".pth", ".onnx")) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "found": []}
    found: list[str] = []
    for child in sorted(path.iterdir(), key=lambda item: item.name.lower()):
        if child.is_file() and child.suffix.lower() in suffixes:
            found.append(child.name)
    return {"path": str(path), "exists": True, "found": found[:100]}


def reference_module_model_status(info: dict[str, Any] | None, *, comfyui_roots: list[Path], app_scope: str = "anima") -> dict[str, Any]:
    info = info or {}
    caps = reference_module_capabilities(info, app_scope=app_scope).get("reference_modules", {})
    model_roots: list[Path] = []
    for root in comfyui_roots:
        if not root:
            continue
        model_roots.extend([root / "models", root / "ComfyUI" / "models"])
    existing_models_root = next((path for path in model_roots if path.exists()), model_roots[0] if model_roots else Path("models"))
    controlnet_choices = _regular_controlnet_choices(info)
    return {
        "ok": True,
        "modules": {
            "outfit": {
                **(caps.get("outfit") or {}),
                "models": {
                    "clip_vision": _scan_model_dir(existing_models_root / "clip_vision"),
                    "ipadapter": _scan_model_dir(existing_models_root / "ipadapter"),
                    "ipadapter_flux": _scan_model_dir(existing_models_root / "ipadapter-flux"),
                },
            },
            "pose": {
                **(caps.get("pose") or {}),
                "models": {
                    "controlnet": {**_scan_model_dir(existing_models_root / "controlnet"), "object_info_choices": controlnet_choices, "lllite_choices": _lllite_choices(info)},
                    "controlnet_aux_ckpts": _scan_model_dir(next((root / "custom_nodes" / "comfyui_controlnet_aux" / "ckpts" for root in comfyui_roots if (root / "custom_nodes").exists()), comfyui_roots[0] / "custom_nodes" / "comfyui_controlnet_aux" / "ckpts" if comfyui_roots else Path("custom_nodes/comfyui_controlnet_aux/ckpts"))),
                },
            },
            "background": {
                **(caps.get("background") or {}),
                "models": {
                    "controlnet": {**_scan_model_dir(existing_models_root / "controlnet"), "object_info_choices": controlnet_choices},
                },
            },
            "anima_lllite": caps.get("anima_lllite") or _anima_lllite_capability(info, app_scope=app_scope),
        },
    }


def apply_outfit_reference_to_workflow(
    workflow: dict[str, Any],
    modules: dict[str, Any],
    *,
    sampler_ids: list[str],
    next_node_id: Callable[[dict[str, Any], int], str],
) -> None:
    outfit = modules.get("outfit") if isinstance(modules.get("outfit"), dict) else {}
    if not outfit.get("apply_to_payload"):
        return
    image_name = str((outfit.get("comfyui_image") or {}).get("name") or outfit.get("image_name") or "")
    apply_node = str(outfit.get("apply_node") or "easy ipadapterApply")
    if not image_name:
        return
    load_id = next_node_id(workflow, 9300)
    workflow[load_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": image_name},
        "_meta": {"title": "Outfit Reference Image"},
    }
    strength = clamp_float(outfit.get("strength"), 0.45)
    start_at = clamp_float(outfit.get("start_at"), 0.0)
    end_at = clamp_float(outfit.get("end_at"), 0.75)
    preset = str(outfit.get("preset") or "REGULAR - FLUX and SD3.5 only (high strength)")
    provider = str(outfit.get("provider") or "CUDA")
    wrapped: dict[str, list[Any]] = {}
    for sampler_id in sampler_ids:
        sampler = workflow.get(str(sampler_id))
        inputs = sampler.get("inputs") if isinstance(sampler, dict) else None
        if not isinstance(inputs, dict) or "model" not in inputs:
            continue
        model_key = repr(inputs.get("model"))
        if model_key not in wrapped:
            node_id = next_node_id(workflow, int(load_id) + len(wrapped) + 1)
            workflow[node_id] = {
                "class_type": apply_node,
                "inputs": {
                    "model": inputs.get("model"),
                    "image": [load_id, 0],
                    "preset": preset,
                    "lora_strength": 0.0,
                    "provider": provider,
                    "weight": strength,
                    "weight_faceidv2": 0.0,
                    "start_at": start_at,
                    "end_at": end_at,
                    "cache_mode": "all",
                    "use_tiled": False,
                },
                "_meta": {"title": "Outfit Reference IP-Adapter"},
            }
            wrapped[model_key] = [node_id, 0]
        inputs["model"] = wrapped[model_key]
    outfit.update(
        {
            "applied": bool(wrapped),
            "apply_node": apply_node,
            "image_name": image_name,
            "strength": strength,
            "start_at": start_at,
            "end_at": end_at,
        }
    )
    modules["outfit"] = outfit


def apply_pose_reference_to_workflow(
    workflow: dict[str, Any],
    modules: dict[str, Any],
    *,
    sampler_ids: list[str],
    next_node_id: Callable[[dict[str, Any], int], str],
) -> None:
    pose = modules.get("pose") if isinstance(modules.get("pose"), dict) else {}
    if not pose.get("apply_to_payload"):
        return
    image_name = str((pose.get("comfyui_image") or {}).get("name") or pose.get("image_name") or "")
    controlnet_model = str(pose.get("controlnet_model") or "")
    if not image_name or not controlnet_model:
        return
    load_id = next_node_id(workflow, 9400)
    control_id = next_node_id(workflow, int(load_id) + 1)
    workflow[load_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": image_name},
        "_meta": {"title": "Pose Reference Image"},
    }
    workflow[control_id] = {
        "class_type": "ControlNetLoader",
        "inputs": {"control_net_name": controlnet_model},
        "_meta": {"title": "Pose Reference ControlNet"},
    }
    control_output: list[Any] = [control_id, 0]
    if pose.get("requires_union_type") or pose.get("union_type"):
        union_id = next_node_id(workflow, int(control_id) + 1)
        workflow[union_id] = {
            "class_type": "SetUnionControlNetType",
            "inputs": {"control_net": [control_id, 0], "type": str(pose.get("union_type") or "openpose")},
            "_meta": {"title": "Pose Reference Union Type"},
        }
        control_output = [union_id, 0]
    strength = clamp_float(pose.get("strength"), 0.75)
    start_at = clamp_float(pose.get("start_at"), 0.0)
    end_at = clamp_float(pose.get("end_at"), 0.85)
    wrapped: dict[str, tuple[list[Any], list[Any]]] = {}
    for sampler_id in sampler_ids:
        sampler = workflow.get(str(sampler_id))
        inputs = sampler.get("inputs") if isinstance(sampler, dict) else None
        if not isinstance(inputs, dict) or "positive" not in inputs or "negative" not in inputs:
            continue
        key = repr((inputs.get("positive"), inputs.get("negative")))
        if key not in wrapped:
            apply_id = next_node_id(workflow, int(control_output[0]) + len(wrapped) + 1)
            workflow[apply_id] = {
                "class_type": "ControlNetApplyAdvanced",
                "inputs": {
                    "positive": inputs.get("positive"),
                    "negative": inputs.get("negative"),
                    "control_net": control_output,
                    "image": [load_id, 0],
                    "strength": strength,
                    "start_percent": start_at,
                    "end_percent": end_at,
                },
                "_meta": {"title": "Pose Reference Apply"},
            }
            wrapped[key] = ([apply_id, 0], [apply_id, 1])
        inputs["positive"], inputs["negative"] = wrapped[key]
    pose.update(
        {
            "applied": bool(wrapped),
            "image_name": image_name,
            "controlnet_model": controlnet_model,
            "strength": strength,
            "start_at": start_at,
            "end_at": end_at,
        }
    )
    modules["pose"] = pose


def _workflow_input_value(value: Any, image_output: list[Any]) -> Any:
    return image_output if value == "__image__" else value


def _int_dimension(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(8, number)


def _background_resize_crop(resize_mode: Any) -> str:
    mode = str(resize_mode or "crop").lower()
    return "center" if mode == "crop" else "disabled"


def apply_background_reference_to_workflow(
    workflow: dict[str, Any],
    modules: dict[str, Any],
    *,
    request: dict[str, Any],
    sampler_ids: list[str],
    next_node_id: Callable[[dict[str, Any], int], str],
) -> None:
    background = modules.get("background") if isinstance(modules.get("background"), dict) else {}
    if not background.get("apply_to_payload"):
        return
    image_name = str((background.get("comfyui_image") or {}).get("name") or background.get("image_name") or "")
    controlnet_model = str(background.get("controlnet_model") or "")
    preprocessor = str(background.get("preprocessor_node_class") or "")
    if not image_name or not controlnet_model or not preprocessor:
        return
    load_id = next_node_id(workflow, 9500)
    next_seed = int(load_id) + 1
    workflow[load_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": image_name},
        "_meta": {"title": "Background Reference Image"},
    }
    image_output: list[Any] = [load_id, 0]
    resize_node = str(background.get("image_resize_node_class") or "")
    if resize_node:
        resize_id = next_node_id(workflow, next_seed)
        next_seed = int(resize_id) + 1
        workflow[resize_id] = {
            "class_type": resize_node,
            "inputs": {
                "image": image_output,
                "width": _int_dimension(request.get("width"), 1024),
                "height": _int_dimension(request.get("height"), 1536),
                "upscale_method": "lanczos",
                "crop": _background_resize_crop(background.get("resize_mode")),
            },
            "_meta": {"title": "Background Reference Resize"},
        }
        image_output = [resize_id, 0]
    preprocessor_id = next_node_id(workflow, next_seed)
    control_id = next_node_id(workflow, int(preprocessor_id) + 1)
    configured_inputs = background.get("preprocessor_inputs") if isinstance(background.get("preprocessor_inputs"), dict) else {}
    preprocessor_inputs = {
        key: _workflow_input_value(value, image_output)
        for key, value in configured_inputs.items()
    }
    preprocessor_inputs.setdefault("image", image_output)
    workflow[preprocessor_id] = {
        "class_type": preprocessor,
        "inputs": preprocessor_inputs,
        "_meta": {"title": "Background Reference Preprocessor"},
    }
    loader_node = str(background.get("loader_node_class") or "ControlNetLoader")
    workflow[control_id] = {
        "class_type": loader_node,
        "inputs": {"control_net_name": controlnet_model},
        "_meta": {"title": "Background Reference ControlNet"},
    }
    strength = clamp_float(background.get("strength"), 0.45, 0.0, 1.5)
    start_at = clamp_float(background.get("start_at"), 0.0)
    end_at = clamp_float(background.get("end_at"), 0.75)
    if end_at < start_at:
        end_at = start_at
    apply_node = str(background.get("apply_node_class") or "ControlNetApplyAdvanced")
    wrapped: dict[str, tuple[list[Any], list[Any]]] = {}
    for sampler_id in sampler_ids:
        sampler = workflow.get(str(sampler_id))
        inputs = sampler.get("inputs") if isinstance(sampler, dict) else None
        if not isinstance(inputs, dict) or "positive" not in inputs or "negative" not in inputs:
            continue
        key = repr((inputs.get("positive"), inputs.get("negative")))
        if key not in wrapped:
            apply_id = next_node_id(workflow, int(control_id) + len(wrapped) + 1)
            workflow[apply_id] = {
                "class_type": apply_node,
                "inputs": {
                    "positive": inputs.get("positive"),
                    "negative": inputs.get("negative"),
                    "control_net": [control_id, 0],
                    "image": [preprocessor_id, 0],
                    "strength": strength,
                    "start_percent": start_at,
                    "end_percent": end_at,
                },
                "_meta": {"title": "Background Reference Apply"},
            }
            wrapped[key] = ([apply_id, 0], [apply_id, 1])
        inputs["positive"], inputs["negative"] = wrapped[key]
    background.update(
        {
            "applied": bool(wrapped),
            "image_name": image_name,
            "controlnet_model": controlnet_model,
            "preprocessor_node_class": preprocessor,
            "image_resize_node_class": resize_node,
            "resize_mode": str(background.get("resize_mode") or "crop").lower(),
            "strength": strength,
            "start_at": start_at,
            "end_at": end_at,
        }
    )
    modules["background"] = background
