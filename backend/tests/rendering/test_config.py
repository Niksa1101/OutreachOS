"""Config validation — reject at load time what would otherwise fail deep in FFmpeg."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from outreachos_backend.rendering.config import (
    BorderConfig,
    OverlayConfig,
    ScreenRecordingJob,
    ShadowConfig,
    TalkingHeadConfig,
)


@pytest.mark.parametrize("color", ["red", "#FFF", "#GGGGGG", "FFFFFF", "#FFFFFFFF", ""])
def test_invalid_hex_colors_are_rejected(color: str) -> None:
    with pytest.raises(ValidationError):
        BorderConfig(color=color)
    with pytest.raises(ValidationError):
        ShadowConfig(color=color)


@pytest.mark.parametrize("color", ["#FFFFFF", "#000000", "#0a0A0f"])
def test_valid_hex_colors_are_accepted(color: str) -> None:
    assert BorderConfig(color=color).color == color


def test_inverted_trim_window_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must be greater than"):
        TalkingHeadConfig(source_path=Path("a.mp4"), trim_start_ms=5000, trim_end_ms=1000)
    with pytest.raises(ValidationError, match="must be greater than"):
        ScreenRecordingJob(
            source_path=Path("a.mp4"),
            output_basename="out",
            trim_start_ms=5000,
            trim_end_ms=1000,
        )


def test_zero_length_trim_window_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must be greater than"):
        TalkingHeadConfig(source_path=Path("a.mp4"), trim_start_ms=1000, trim_end_ms=1000)


def test_open_ended_trim_window_is_allowed() -> None:
    head = TalkingHeadConfig(source_path=Path("a.mp4"), trim_start_ms=1000)
    assert head.trim_end_ms is None


def test_overlay_defaults_round_trip() -> None:
    overlay = OverlayConfig()
    assert OverlayConfig.model_validate(overlay.model_dump(mode="json")) == overlay
