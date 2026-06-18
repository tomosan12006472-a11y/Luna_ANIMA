from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    workflow_mode: str = "anima"
    character1: str = "Random"
    character2: str = "None"
    character3: str = "None"
    character1_role: str = "main"
    character2_role: str = "left"
    character3_role: str = "right"
    original_character: str = "None"
    character1_weight: float = 1.0
    character2_weight: float = 1.0
    character3_weight: float = 1.0
    original_weight: float = 1.0
    rating: str = "safe"
    rating_prompt_overrides: dict[str, str] = Field(default_factory=dict)
    quality_preset: str = "standard"
    quality_prompt_overrides: dict[str, str] = Field(default_factory=dict)
    negative_preset: str = "anima_recommended"
    meta_prompt: str = "anime illustration"
    year_prompt: str = ""
    outfit_prompt: str = ""
    expression_prompt: str = ""
    pose_prompt: str = ""
    background_prompt: str = ""
    camera_prompt: str = ""
    lighting_prompt: str = ""
    natural_description: str = ""
    common_prompt: str = ""
    positive_prompt: str = ""
    negative_prompt: str = ""
    negative_prompt_raw: str = ""
    negative_prompt_mode: str = "append"
    prompt_ban: str = ""
    view_prompt: str = ""
    model: str = "Anima\\anima-preview3-base.safetensors"
    text_encoder: str = "qwen_3_06b_base.safetensors"
    vae: str = "qwen_image_vae.safetensors"
    width: int = 1024
    height: int = 1536
    steps: int = 32
    cfg: float = 4.5
    shift: float | None = None
    sampler: str = "er_sde"
    scheduler: str = "simple"
    seed_mode: str = "fixed"
    seed: int = -1
    loras: list[dict[str, Any]] = Field(default_factory=list)
    hires_fix: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    official_loras: dict[str, Any] = Field(default_factory=dict)
    reference_assist: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    reference_modules: dict[str, Any] = Field(default_factory=lambda: {"enabled": True})
    image_to_image: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    dynamic_prompt: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    prompt_random_collect: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    face_detailer: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    hand_detailer: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    reset_comfy_cache: bool = False
    wait: bool = False
    count: int = 1


class FaceDetailerPostprocessRequest(BaseModel):
    history_id: str
    settings: dict[str, Any] = Field(default_factory=dict)


class HandDetailerPostprocessRequest(BaseModel):
    history_id: str
    settings: dict[str, Any] = Field(default_factory=dict)


class DynamicPromptPreviewRequest(BaseModel):
    positive_prompt: str = ""
    negative_prompt: str = ""
    seed: int = 0
    enabled: bool = True


class QueueCancelRequest(BaseModel):
    prompt_id: str = ""
