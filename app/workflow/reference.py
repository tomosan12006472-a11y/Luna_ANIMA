from __future__ import annotations

from typing import Any

from .._shared_utils import next_node_id
from ..reference_modules import apply_outfit_reference_to_workflow, apply_pose_reference_to_workflow


def apply_reference_modules(workflow: dict[str, Any], request: dict[str, Any]) -> None:
    modules = request.get("reference_modules") if isinstance(request.get("reference_modules"), dict) else {}
    apply_outfit_reference_to_workflow(workflow, modules, sampler_ids=["19"], next_node_id=next_node_id)
    apply_pose_reference_to_workflow(workflow, modules, sampler_ids=["19"], next_node_id=next_node_id)
    request["reference_modules"] = modules

def apply_reference_assist(workflow: dict[str, Any], request: dict[str, Any]) -> None:
    ref = request.get("reference_assist") if isinstance(request.get("reference_assist"), dict) else {}
    if not ref.get("apply_to_payload"):
        return
    image_name = str((ref.get("comfyui_image") or {}).get("name") or ref.get("image_name") or "")
    controlnet_model = str(ref.get("controlnet_model") or "")
    if not image_name or not controlnet_model:
        return
    apply_node_type = str(ref.get("apply_node_type") or "ControlNetApplyAdvanced")
    strength = max(0.0, min(1.0, float(ref.get("strength") or 0.25)))
    start_percent = max(0.0, min(1.0, float(ref.get("start_percent") or 0.0)))
    end_percent = max(0.0, min(1.0, float(ref.get("end_percent") or 0.65)))
    load_id = next_node_id(workflow)
    control_id = next_node_id(workflow, int(load_id) + 1)
    workflow[load_id] = {
        "inputs": {"image": image_name},
        "class_type": "LoadImage",
        "_meta": {"title": "Reference Assist Image"},
    }
    workflow[control_id] = {
        "inputs": {"control_net_name": controlnet_model},
        "class_type": "ControlNetLoader",
        "_meta": {"title": "Reference Assist ControlNet"},
    }
    control_output: list[Any] = [control_id, 0]
    if ref.get("has_union_type"):
        union_id = next_node_id(workflow, int(control_id) + 1)
        workflow[union_id] = {
            "inputs": {"control_net": [control_id, 0], "type": str(ref.get("union_type") or "auto")},
            "class_type": "SetUnionControlNetType",
            "_meta": {"title": "Reference Assist Union Type"},
        }
        control_output = [union_id, 0]
    sampler = workflow.get("19")
    inputs = sampler.get("inputs") if isinstance(sampler, dict) else None
    if not isinstance(inputs, dict) or "positive" not in inputs or "negative" not in inputs:
        return
    apply_id = next_node_id(workflow, int(control_output[0]) + 1)
    if apply_node_type == "ControlNetApplyAdvanced":
        apply_inputs: dict[str, Any] = {
            "positive": inputs.get("positive"),
            "negative": inputs.get("negative"),
            "control_net": control_output,
            "image": [load_id, 0],
            "strength": strength,
            "start_percent": start_percent,
            "end_percent": end_percent,
        }
        positive_output = [apply_id, 0]
        negative_output = [apply_id, 1]
    else:
        apply_inputs = {
            "conditioning": inputs.get("positive"),
            "control_net": control_output,
            "image": [load_id, 0],
            "strength": strength,
        }
        positive_output = [apply_id, 0]
        negative_output = inputs.get("negative")
    workflow[apply_id] = {
        "inputs": apply_inputs,
        "class_type": apply_node_type,
        "_meta": {"title": "Reference Assist Apply"},
    }
    inputs["positive"] = positive_output
    inputs["negative"] = negative_output
