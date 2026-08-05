"""Shared configuration models for the headless render CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

Anchor = Literal["top_left", "top_right", "bottom_left", "bottom_right"]
Shape = Literal["circle", "rounded_rect", "rect"]
QualityPreset = Literal["draft", "standard", "high"]
AnimationType = Literal["fade"]

# overlay_assets._hex_rgba only understands 6-digit hex; catch it at load time
# rather than as a bare ValueError deep inside Pillow drawing.
HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"


class TrimmableSource(BaseModel):
    """A media source with an optional trim window."""

    source_path: Path
    trim_start_ms: int = Field(default=0, ge=0)
    trim_end_ms: int | None = None

    @model_validator(mode="after")
    def _check_trim_window(self) -> Self:
        if self.trim_end_ms is not None and self.trim_end_ms <= self.trim_start_ms:
            raise ValueError(
                f"trim_end_ms ({self.trim_end_ms}) must be greater than "
                f"trim_start_ms ({self.trim_start_ms})"
            )
        return self


class SizeConfig(BaseModel):
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class OffsetConfig(BaseModel):
    x: int
    y: int


class BorderConfig(BaseModel):
    enabled: bool = True
    width: int = Field(default=4, ge=0)
    color: str = Field(default="#FFFFFF", pattern=HEX_COLOR)


class ShadowConfig(BaseModel):
    enabled: bool = True
    blur: int = Field(default=32, ge=0)
    offset_x: int = 0
    offset_y: int = 8
    opacity: float = Field(default=0.45, ge=0.0, le=1.0)
    color: str = Field(default="#000000", pattern=HEX_COLOR)


class BackgroundConfig(BaseModel):
    enabled: bool = False
    color: str = Field(default="#0A0A0A", pattern=HEX_COLOR)


class AnimationConfig(BaseModel):
    type: AnimationType = "fade"
    duration_ms: int = Field(default=500, ge=0)


class OverlayConfig(BaseModel):
    schema_version: int = 1
    anchor: Anchor = "bottom_right"
    size: SizeConfig = Field(default_factory=lambda: SizeConfig(width=480, height=480))
    offset: OffsetConfig = Field(default_factory=lambda: OffsetConfig(x=48, y=48))
    shape: Shape = "circle"
    border_radius: int = Field(default=24, ge=0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    padding: int = Field(default=0, ge=0)
    border: BorderConfig = Field(default_factory=BorderConfig)
    shadow: ShadowConfig = Field(default_factory=ShadowConfig)
    background: BackgroundConfig = Field(default_factory=BackgroundConfig)
    animation: AnimationConfig = Field(default_factory=AnimationConfig)


class TalkingHeadConfig(TrimmableSource):
    focal_x: float = Field(default=0.5, ge=0.0, le=1.0)
    focal_y: float = Field(default=0.5, ge=0.0, le=1.0)


class ScreenRecordingJob(TrimmableSource):
    output_basename: str


class RenderBatchConfig(BaseModel):
    talking_head: TalkingHeadConfig
    overlay: OverlayConfig
    recordings: list[ScreenRecordingJob]
    quality: QualityPreset = "standard"
    encoder: str | None = None
    """Override auto-detect; golden tests force libx264."""

    owner_ref: str = "cli-batch"
    owner_kind: str = "cli"
