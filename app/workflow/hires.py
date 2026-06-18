from __future__ import annotations

import math
from typing import Any

from .._shared_utils import next_node_id
from .prompts import is_lora_sample_mode


def round_to_multiple(value: float, multiple: int = 8) -> int:
    if value <= 0:
        return multiple
    return max(multiple, int(round(value / multiple) * multiple))


def compute_hires_size(request: dict[str, Any]) -> dict[str, Any]:
    base_width = int(request.get("width") or 1024)
    base_height = int(request.get("height") or 1536)
    hires_fix = request.get("hires_fix") or {}
    enabled = bool(hires_fix.get("enabled"))
    factor = float(hires_fix.get("upscale_factor") or 1.0)
    target_width = int(hires_fix.get("target_width") or 0)
    target_height = int(hires_fix.get("target_height") or 0)
    if not enabled:
        factor = 1.0
        final_width = base_width
        final_height = base_height
    elif target_width > 0 and target_height > 0:
        final_width = round_to_multiple(target_width)
        final_height = round_to_multiple(target_height)
        factor = max(final_width / base_width, final_height / base_height)
    else:
        factor = factor if math.isfinite(factor) and factor > 1.0 else 1.0
        final_width = round_to_multiple(base_width * factor)
        final_height = round_to_multiple(base_height * factor)
    return {
        "base_width": base_width,
        "base_height": base_height,
        "enabled": enabled,
        "factor": factor,
        "target_width": target_width or None,
        "target_height": target_height or None,
        "final_width": final_width,
        "final_height": final_height,
    }


def apply_hires_fix(workflow: dict[str, Any], request: dict[str, Any]) -> None:
    hires = request.get("hires_fix") if isinstance(request.get("hires_fix"), dict) else {}
    if is_lora_sample_mode(request) or not hires.get("enabled"):
        return

    size = compute_hires_size(request)
    mode = str(hires.get("mode") or "latent").lower()
    sampler_inputs = workflow["19"]["inputs"]
    steps = int(hires.get("steps") or 15)
    denoise = float(hires.get("denoise") or 0.45)

    def hires_sampler_inputs(latent_image: list[Any]) -> dict[str, Any]:
        return {
            "model": sampler_inputs.get("model"),
            "positive": sampler_inputs.get("positive"),
            "negative": sampler_inputs.get("negative"),
            "seed": sampler_inputs.get("seed"),
            "steps": steps,
            "cfg": sampler_inputs.get("cfg"),
            "sampler_name": sampler_inputs.get("sampler_name"),
            "scheduler": sampler_inputs.get("scheduler"),
            "denoise": denoise,
            "latent_image": latent_image,
        }

    if mode == "model":
        upscale_model = str(hires.get("upscale_model") or "").strip()
        if not upscale_model:
            raise ValueError("Hires.fix model mode requires upscale_model.")
        load_id = next_node_id(workflow, 9200)
        upscale_id = next_node_id(workflow, int(load_id) + 1)
        scale_id = next_node_id(workflow, int(upscale_id) + 1)
        encode_id = next_node_id(workflow, int(scale_id) + 1)
        sampler_id = next_node_id(workflow, int(encode_id) + 1)
        decode_id = next_node_id(workflow, int(sampler_id) + 1)
        workflow[load_id] = {
            "class_type": "UpscaleModelLoader",
            "inputs": {"model_name": upscale_model},
            "_meta": {"title": "Hires Fix Upscale Model"},
        }
        workflow[upscale_id] = {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {"upscale_model": [load_id, 0], "image": ["8", 0]},
            "_meta": {"title": "Hires Fix Image Upscale"},
        }
        workflow[scale_id] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": [upscale_id, 0],
                "width": size["final_width"],
                "height": size["final_height"],
                "upscale_method": "lanczos",
                "crop": "disabled",
            },
            "_meta": {"title": "Hires Fix Image Scale"},
        }
        workflow[encode_id] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": [scale_id, 0], "vae": ["15", 0]},
            "_meta": {"title": "Hires Fix VAE Encode"},
        }
        workflow[sampler_id] = {
            "class_type": "KSampler",
            "inputs": hires_sampler_inputs([encode_id, 0]),
            "_meta": {"title": "Hires Fix KSampler"},
        }
    else:
        mode = "latent"
        upscale_id = next_node_id(workflow, 9200)
        sampler_id = next_node_id(workflow, int(upscale_id) + 1)
        decode_id = next_node_id(workflow, int(sampler_id) + 1)
        workflow[upscale_id] = {
            "class_type": "LatentUpscaleBy",
            "inputs": {
                "samples": ["19", 0],
                "upscale_method": str(hires.get("latent_upscale_method") or hires.get("upscale_method") or "nearest-exact"),
                "scale_by": size["factor"],
            },
            "_meta": {"title": "Hires Fix Latent Upscale"},
        }
        workflow[sampler_id] = {
            "class_type": "KSampler",
            "inputs": hires_sampler_inputs([upscale_id, 0]),
            "_meta": {"title": "Hires Fix KSampler"},
        }

    workflow[decode_id] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": [sampler_id, 0], "vae": ["15", 0]},
        "_meta": {"title": "Hires Fix VAE Decode"},
    }
    workflow["1"]["inputs"]["images"] = [decode_id, 0]
    hires.update(
        {
            "applied": True,
            "mode": mode,
            "final_width": size["final_width"],
            "final_height": size["final_height"],
            "factor": size["factor"],
        }
    )
    request["hires_fix"] = hires
