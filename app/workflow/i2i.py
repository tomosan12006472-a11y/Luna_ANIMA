from __future__ import annotations

from typing import Any

from .._shared_utils import next_node_id


def apply_image_to_image(workflow: dict[str, Any], request: dict[str, Any]) -> None:
    i2i = request.get("image_to_image") if isinstance(request.get("image_to_image"), dict) else {}
    if not i2i.get("apply_to_payload"):
        return
    image_name = str((i2i.get("comfyui_image") or {}).get("name") or i2i.get("image_name") or i2i.get("prepared_filename") or "")
    if not image_name:
        i2i["apply_to_payload"] = False
        i2i["unsupported_reason"] = "missing ComfyUI i2i image"
        request["image_to_image"] = i2i
        return
    denoise = max(0.01, min(1.0, float(i2i.get("denoise") or 0.45)))
    load_id = next_node_id(workflow)
    encode_id = next_node_id(workflow, int(load_id) + 1)
    workflow[load_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": image_name},
        "_meta": {"title": "Image to Image Source"},
    }
    workflow[encode_id] = {
        "class_type": "VAEEncode",
        "inputs": {"pixels": [load_id, 0], "vae": ["15", 0]},
        "_meta": {"title": "Image to Image VAE Encode"},
    }
    workflow["19"]["inputs"]["latent_image"] = [encode_id, 0]
    workflow["19"]["inputs"]["denoise"] = denoise
    i2i.update(
        {
            "applied": True,
            "mode": "generation",
            "denoise": denoise,
            "image_name": image_name,
            "sampler_node": "19",
            "load_image_node": load_id,
            "latent_node": encode_id,
        }
    )
    request["image_to_image"] = i2i
