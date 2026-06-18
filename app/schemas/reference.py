from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


def _string_value(value: Any) -> str:
    return str(value or "")


def _comfyui_image(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {"name": None, "subfolder": "", "type": "input"}


class CompatSettingsModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ReferenceAssistSettings(CompatSettingsModel):
    enabled: bool = False
    mode: str = "auto"
    experimental: bool = False
    app_scope: str = "anima"
    image_id: str = ""
    image_name: str = ""
    controlnet_model: str = ""
    strength: float = 0.25
    start_percent: float = 0.0
    end_percent: float = 0.75
    resize_mode: str = "fit"
    union_type: str = "auto"
    comfyui_image: dict[str, Any] = Field(default_factory=lambda: {"name": None, "subfolder": "", "type": "input"})

    @field_validator("enabled", "experimental", mode="before")
    @classmethod
    def _normalize_bool(cls, value: Any) -> bool:
        return _bool_value(value)

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: Any) -> str:
        mode = str(value or "auto")
        return mode if mode in {"auto", "controlnet", "img2img_reference"} else "auto"

    @field_validator("image_id", "image_name", "controlnet_model", "resize_mode", "union_type", "app_scope", mode="before")
    @classmethod
    def _normalize_string(cls, value: Any) -> str:
        return _string_value(value)

    @field_validator("strength", mode="before")
    @classmethod
    def _normalize_strength(cls, value: Any) -> float:
        return _clamp_float(value, 0.25)

    @field_validator("start_percent", mode="before")
    @classmethod
    def _normalize_start(cls, value: Any) -> float:
        return _clamp_float(value, 0.0)

    @field_validator("end_percent", mode="before")
    @classmethod
    def _normalize_end(cls, value: Any) -> float:
        return _clamp_float(value, 0.75)

    @field_validator("comfyui_image", mode="before")
    @classmethod
    def _normalize_comfyui_image(cls, value: Any) -> dict[str, Any]:
        return _comfyui_image(value)


class ImageToImageSettings(CompatSettingsModel):
    enabled: bool = False
    app_scope: str = "anima"
    image_id: str = ""
    source: str = ""
    source_history_id: str = ""
    denoise: float = 0.45
    resize_mode: str = "fit"
    use_source_size: bool = False
    allow_with_hires_fix: bool = False
    allow_with_reference_assist: bool = False
    comfyui_image: dict[str, Any] = Field(default_factory=lambda: {"name": None, "subfolder": "", "type": "input"})

    @field_validator("enabled", "use_source_size", "allow_with_hires_fix", "allow_with_reference_assist", mode="before")
    @classmethod
    def _normalize_bool(cls, value: Any) -> bool:
        return _bool_value(value)

    @field_validator("app_scope", "image_id", "source", "source_history_id", mode="before")
    @classmethod
    def _normalize_string(cls, value: Any) -> str:
        return _string_value(value)

    @field_validator("denoise", mode="before")
    @classmethod
    def _normalize_denoise(cls, value: Any) -> float:
        return _clamp_float(value, 0.45, 0.01, 1.0)

    @field_validator("resize_mode", mode="before")
    @classmethod
    def _normalize_resize_mode(cls, value: Any) -> str:
        resize_mode = str(value or "fit").lower()
        return resize_mode if resize_mode in {"fit", "cover", "stretch"} else "fit"

    @field_validator("comfyui_image", mode="before")
    @classmethod
    def _normalize_comfyui_image(cls, value: Any) -> dict[str, Any]:
        return _comfyui_image(value)


class ReferenceModuleItemSettings(CompatSettingsModel):
    enabled: bool = False
    image_id: str = ""
    image_name: str = ""
    strength: float = 0.0
    start_at: float = 0.0
    end_at: float = 1.0
    comfyui_image: dict[str, Any] = Field(default_factory=lambda: {"name": None, "subfolder": "", "type": "input"})

    @field_validator("enabled", mode="before")
    @classmethod
    def _normalize_bool(cls, value: Any) -> bool:
        return _bool_value(value)

    @field_validator("image_id", "image_name", mode="before")
    @classmethod
    def _normalize_string(cls, value: Any) -> str:
        return _string_value(value)

    @field_validator("strength", mode="before")
    @classmethod
    def _normalize_strength(cls, value: Any) -> float:
        return _clamp_float(value, 0.0)

    @field_validator("start_at", mode="before")
    @classmethod
    def _normalize_start(cls, value: Any) -> float:
        return _clamp_float(value, 0.0)

    @field_validator("end_at", mode="before")
    @classmethod
    def _normalize_end(cls, value: Any) -> float:
        return _clamp_float(value, 1.0)

    @field_validator("comfyui_image", mode="before")
    @classmethod
    def _normalize_comfyui_image(cls, value: Any) -> dict[str, Any]:
        return _comfyui_image(value)

    @model_validator(mode="after")
    def _order_range(self) -> "ReferenceModuleItemSettings":
        if self.end_at < self.start_at:
            self.end_at = self.start_at
        return self


class OutfitReferenceModuleSettings(ReferenceModuleItemSettings):
    strength: float = 0.45
    mode: str = "image_prompt"
    strategy: str = "ip_adapter"
    crop_mode: str = "user_prepared"
    start_at: float = 0.0
    end_at: float = 0.75
    preset: str = "REGULAR - FLUX and SD3.5 only (high strength)"
    provider: str = "CUDA"

    @field_validator("strength", mode="before")
    @classmethod
    def _normalize_outfit_strength(cls, value: Any) -> float:
        return _clamp_float(value, 0.45)

    @field_validator("end_at", mode="before")
    @classmethod
    def _normalize_outfit_end(cls, value: Any) -> float:
        return _clamp_float(value, 0.75)

    @field_validator("mode", "crop_mode", "preset", "provider", mode="before")
    @classmethod
    def _normalize_optional_string(cls, value: Any) -> str:
        return _string_value(value)

    @model_validator(mode="after")
    def _fill_outfit_defaults(self) -> "OutfitReferenceModuleSettings":
        self.mode = self.mode or "image_prompt"
        self.strategy = "ip_adapter"
        self.crop_mode = self.crop_mode or "user_prepared"
        self.preset = self.preset or "REGULAR - FLUX and SD3.5 only (high strength)"
        self.provider = self.provider or "CUDA"
        return self


class PoseReferenceModuleSettings(ReferenceModuleItemSettings):
    strength: float = 0.75
    mode: str = "pose_image"
    start_at: float = 0.0
    end_at: float = 0.85
    strategy: str = "controlnet_openpose"
    controlnet_model: str = ""
    union_type: str = "openpose"

    @field_validator("strength", mode="before")
    @classmethod
    def _normalize_pose_strength(cls, value: Any) -> float:
        return _clamp_float(value, 0.75)

    @field_validator("end_at", mode="before")
    @classmethod
    def _normalize_pose_end(cls, value: Any) -> float:
        return _clamp_float(value, 0.85)

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_pose_mode(cls, value: Any) -> str:
        mode = str(value or "pose_image")
        return mode if mode in {"pose_image", "auto_dwpose"} else "pose_image"

    @field_validator("controlnet_model", "union_type", mode="before")
    @classmethod
    def _normalize_optional_string(cls, value: Any) -> str:
        return _string_value(value)

    @model_validator(mode="after")
    def _fill_pose_defaults(self) -> "PoseReferenceModuleSettings":
        self.strategy = "controlnet_openpose"
        self.union_type = self.union_type or "openpose"
        return self


class ReferenceModulesSettings(CompatSettingsModel):
    enabled: bool = True
    preset: str = ""
    outfit: OutfitReferenceModuleSettings = Field(default_factory=OutfitReferenceModuleSettings)
    pose: PoseReferenceModuleSettings = Field(default_factory=PoseReferenceModuleSettings)

    @field_validator("enabled", mode="before")
    @classmethod
    def _normalize_bool(cls, value: Any) -> bool:
        return _bool_value(True if value is None else value)

    @field_validator("preset", mode="before")
    @classmethod
    def _normalize_preset(cls, value: Any) -> str:
        return str(value or "")

    @model_validator(mode="before")
    @classmethod
    def _normalize_raw(cls, value: Any) -> Any:
        return value if isinstance(value, dict) else {}

    @model_validator(mode="after")
    def _derive_preset(self) -> "ReferenceModulesSettings":
        if not self.preset:
            self.preset = (
                "outfit_pose"
                if self.outfit.enabled and self.pose.enabled
                else "outfit_only"
                if self.outfit.enabled
                else "pose_only"
                if self.pose.enabled
                else "off"
            )
        return self


class I2IFromHistoryRequest(BaseModel):
    history_id: str
