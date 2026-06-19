from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .reference import ImageToImageSettings, ReferenceAssistSettings, ReferenceModulesSettings


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "off", "no"}
    return bool(value)


def _clamp_float(value: Any, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _string_value(value: Any) -> str:
    return str(value or "")


def _clamp_text(value: Any, default: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        text = default
    return text[:limit]


class CompatSettingsModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class HiresFixSettings(CompatSettingsModel):
    enabled: bool = False
    mode: str = "latent"
    upscale_factor: float = 1.0
    target_width: int | None = None
    target_height: int | None = None
    latent_upscale_method: str = "bicubic"
    upscale_method: str = ""
    upscale_model: str = ""
    denoise: float = 0.45
    steps: int = 15

    @field_validator("enabled", mode="before")
    @classmethod
    def _normalize_bool(cls, value: Any) -> bool:
        return _bool_value(value)

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: Any) -> str:
        mode = str(value or "latent").lower()
        return mode if mode in {"latent", "model"} else "latent"

    @field_validator("upscale_factor", mode="before")
    @classmethod
    def _normalize_factor(cls, value: Any) -> float:
        return _clamp_float(value, 1.0, 1.0, 4.0)

    @field_validator("target_width", "target_height", mode="before")
    @classmethod
    def _normalize_optional_dimension(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        return _clamp_int(value, 0, 0, 8192) or None

    @field_validator("latent_upscale_method", mode="before")
    @classmethod
    def _normalize_latent_method(cls, value: Any) -> str:
        method = str(value or "bicubic")
        return method if method in {"nearest-exact", "bilinear", "area", "bicubic", "bislerp", "lanczos"} else "bicubic"

    @field_validator("upscale_method", "upscale_model", mode="before")
    @classmethod
    def _normalize_string(cls, value: Any) -> str:
        return _string_value(value)

    @field_validator("denoise", mode="before")
    @classmethod
    def _normalize_denoise(cls, value: Any) -> float:
        return _clamp_float(value, 0.45, 0.0, 1.0)

    @field_validator("steps", mode="before")
    @classmethod
    def _normalize_steps(cls, value: Any) -> int:
        return _clamp_int(value, 15, 1, 60)


class OfficialHighresLoraSettings(CompatSettingsModel):
    enabled: bool = False
    strength: float = 0.6

    @field_validator("enabled", mode="before")
    @classmethod
    def _normalize_bool(cls, value: Any) -> bool:
        return _bool_value(value)

    @field_validator("strength", mode="before")
    @classmethod
    def _normalize_strength(cls, value: Any) -> float:
        return _clamp_float(value, 0.6, 0.0, 1.0)


class OfficialTurboLoraSettings(OfficialHighresLoraSettings):
    version: str = "auto"
    preset_applied: bool = False

    @field_validator("version", mode="before")
    @classmethod
    def _normalize_version(cls, value: Any) -> str:
        version = str(value or "auto")
        return version if version in {"auto", "v0.1", "v0.2"} else "auto"

    @field_validator("preset_applied", mode="before")
    @classmethod
    def _normalize_preset_bool(cls, value: Any) -> bool:
        return _bool_value(value)


class OfficialLorasSettings(CompatSettingsModel):
    highres: OfficialHighresLoraSettings = Field(default_factory=OfficialHighresLoraSettings)
    turbo: OfficialTurboLoraSettings = Field(default_factory=OfficialTurboLoraSettings)

    @model_validator(mode="before")
    @classmethod
    def _normalize_raw(cls, value: Any) -> Any:
        return value if isinstance(value, dict) else {}


class DynamicPromptSettings(CompatSettingsModel):
    enabled: bool = False
    wildcard_seed: int | None = None

    @field_validator("enabled", mode="before")
    @classmethod
    def _normalize_bool(cls, value: Any) -> bool:
        return _bool_value(value)

    @field_validator("wildcard_seed", mode="before")
    @classmethod
    def _normalize_seed(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        return _clamp_int(value, 0, 0, 4294967295)

    @model_validator(mode="before")
    @classmethod
    def _seed_alias(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {}
        if "wildcard_seed" not in value and "seed" in value:
            value = {**value, "wildcard_seed": value.get("seed")}
        return value


class PromptRandomCollectSettings(CompatSettingsModel):
    enabled: bool = False
    mode: str = "random"
    instruction: str = ""
    strength: str = "standard"
    include_characters: bool = True
    use_character_motifs: bool = True

    @field_validator("enabled", "include_characters", "use_character_motifs", mode="before")
    @classmethod
    def _normalize_bool(cls, value: Any) -> bool:
        return _bool_value(value)

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: Any) -> str:
        mode = str(value or "random").strip().lower()
        return mode if mode in {"random", "positive_completion"} else "random"

    @field_validator("strength", mode="before")
    @classmethod
    def _normalize_strength(cls, value: Any) -> str:
        strength = str(value or "standard").strip().lower()
        return strength if strength in {"subtle", "standard", "reference_568", "legacy_568", "rich"} else "standard"

    @model_validator(mode="after")
    def _normalize_instruction(self) -> "PromptRandomCollectSettings":
        defaults = {
            "random": "衣装、表情、背景、小物をランダムに足す",
            "positive_completion": "既存Positiveの意図を保ったまま、不足している描写を英語タグで補う",
        }
        self.instruction = _clamp_text(self.instruction, defaults.get(self.mode, defaults["random"]), 1000)
        if not self.include_characters:
            self.use_character_motifs = False
        return self


class FaceDetailerRequestSettings(CompatSettingsModel):
    enabled: bool = False
    mode: str = "generation"
    detector: str = "bbox/face_yolov8m.pt"
    steps: int = 12
    cfg: float = 5.0
    denoise: float = 0.3
    guide_size: int = 512
    max_size: int = 1024
    bbox_threshold: float = 0.65
    bbox_dilation: int = 10
    bbox_crop_factor: float = 3.0
    drop_size: int = 64
    sam_enabled: bool = False
    seed_policy: str = "image_seed_plus_offset"
    seed_offset: int = 100000

    @field_validator("enabled", "sam_enabled", mode="before")
    @classmethod
    def _normalize_bool(cls, value: Any) -> bool:
        return _bool_value(value)

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: Any) -> str:
        return "postprocess" if str(value or "") == "postprocess" else "generation"

    @field_validator("detector", "seed_policy", mode="before")
    @classmethod
    def _normalize_string(cls, value: Any) -> str:
        return _string_value(value)

    @field_validator("steps", mode="before")
    @classmethod
    def _normalize_steps(cls, value: Any) -> int:
        return _clamp_int(value, 12, 1, 60)

    @field_validator("cfg", mode="before")
    @classmethod
    def _normalize_cfg(cls, value: Any) -> float:
        return _clamp_float(value, 5.0, 0.0, 30.0)

    @field_validator("denoise", mode="before")
    @classmethod
    def _normalize_denoise(cls, value: Any) -> float:
        return _clamp_float(value, 0.3, 0.0, 1.0)

    @field_validator("guide_size", mode="before")
    @classmethod
    def _normalize_guide_size(cls, value: Any) -> int:
        return _clamp_int(value, 512, 64, 2048)

    @field_validator("max_size", mode="before")
    @classmethod
    def _normalize_max_size(cls, value: Any) -> int:
        return _clamp_int(value, 1024, 128, 4096)

    @field_validator("bbox_threshold", mode="before")
    @classmethod
    def _normalize_bbox_threshold(cls, value: Any) -> float:
        return _clamp_float(value, 0.65, 0.0, 1.0)

    @field_validator("bbox_dilation", mode="before")
    @classmethod
    def _normalize_bbox_dilation(cls, value: Any) -> int:
        return _clamp_int(value, 10, -512, 512)

    @field_validator("bbox_crop_factor", mode="before")
    @classmethod
    def _normalize_bbox_crop_factor(cls, value: Any) -> float:
        return _clamp_float(value, 3.0, 1.0, 10.0)

    @field_validator("drop_size", mode="before")
    @classmethod
    def _normalize_drop_size(cls, value: Any) -> int:
        return _clamp_int(value, 64, 4, 512)

    @field_validator("seed_offset", mode="before")
    @classmethod
    def _normalize_seed_offset(cls, value: Any) -> int:
        return _clamp_int(value, 100000, 0, 2147483647)


class HandDetailerRequestSettings(FaceDetailerRequestSettings):
    detector: str = "bbox/hand_yolov8s.pt"
    steps: int = 14
    cfg: float = 4.0
    denoise: float = 0.45
    bbox_threshold: float = 0.35
    bbox_dilation: int = 16
    bbox_crop_factor: float = 2.5
    drop_size: int = 24
    seed_offset: int = 200000
    lllite_enabled: bool = True
    lllite_model: str = "anima-lllite-inpainting-v2.safetensors"
    lllite_strength: float = 0.85
    lllite_start: float = 0.0
    lllite_end: float = 1.0

    @field_validator("steps", mode="before")
    @classmethod
    def _normalize_hand_steps(cls, value: Any) -> int:
        return _clamp_int(value, 14, 1, 60)

    @field_validator("cfg", mode="before")
    @classmethod
    def _normalize_hand_cfg(cls, value: Any) -> float:
        return _clamp_float(value, 4.0, 0.0, 30.0)

    @field_validator("denoise", mode="before")
    @classmethod
    def _normalize_hand_denoise(cls, value: Any) -> float:
        return _clamp_float(value, 0.45, 0.0, 1.0)

    @field_validator("bbox_threshold", mode="before")
    @classmethod
    def _normalize_hand_bbox_threshold(cls, value: Any) -> float:
        return _clamp_float(value, 0.35, 0.0, 1.0)

    @field_validator("bbox_dilation", mode="before")
    @classmethod
    def _normalize_hand_bbox_dilation(cls, value: Any) -> int:
        return _clamp_int(value, 16, -512, 512)

    @field_validator("bbox_crop_factor", mode="before")
    @classmethod
    def _normalize_hand_bbox_crop_factor(cls, value: Any) -> float:
        return _clamp_float(value, 2.5, 1.0, 10.0)

    @field_validator("drop_size", mode="before")
    @classmethod
    def _normalize_hand_drop_size(cls, value: Any) -> int:
        return _clamp_int(value, 24, 4, 512)

    @field_validator("seed_offset", mode="before")
    @classmethod
    def _normalize_hand_seed_offset(cls, value: Any) -> int:
        return _clamp_int(value, 200000, 0, 2147483647)

    @field_validator("lllite_enabled", mode="before")
    @classmethod
    def _normalize_lllite_enabled(cls, value: Any) -> bool:
        return _bool_value(True if value is None else value)

    @field_validator("lllite_model", mode="before")
    @classmethod
    def _normalize_lllite_model(cls, value: Any) -> str:
        return str(value or "anima-lllite-inpainting-v2.safetensors")

    @field_validator("lllite_strength", mode="before")
    @classmethod
    def _normalize_lllite_strength(cls, value: Any) -> float:
        return _clamp_float(value, 0.85, 0.0, 10.0)

    @field_validator("lllite_start", mode="before")
    @classmethod
    def _normalize_lllite_start(cls, value: Any) -> float:
        return _clamp_float(value, 0.0, 0.0, 1.0)

    @field_validator("lllite_end", mode="before")
    @classmethod
    def _normalize_lllite_end(cls, value: Any) -> float:
        return _clamp_float(value, 1.0, 0.0, 1.0)

    @model_validator(mode="after")
    def _order_lllite_range(self) -> "HandDetailerRequestSettings":
        if self.lllite_end < self.lllite_start:
            self.lllite_end = self.lllite_start
        return self


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
    hires_fix: HiresFixSettings = Field(default_factory=HiresFixSettings)
    official_loras: OfficialLorasSettings = Field(default_factory=OfficialLorasSettings)
    reference_assist: ReferenceAssistSettings = Field(default_factory=ReferenceAssistSettings)
    reference_modules: ReferenceModulesSettings = Field(default_factory=ReferenceModulesSettings)
    image_to_image: ImageToImageSettings = Field(default_factory=ImageToImageSettings)
    dynamic_prompt: DynamicPromptSettings = Field(default_factory=DynamicPromptSettings)
    prompt_random_collect: PromptRandomCollectSettings = Field(default_factory=PromptRandomCollectSettings)
    face_detailer: FaceDetailerRequestSettings = Field(default_factory=FaceDetailerRequestSettings)
    hand_detailer: HandDetailerRequestSettings = Field(default_factory=HandDetailerRequestSettings)
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
