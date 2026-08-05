"""Assemble per-video and alpha filtergraphs from step lists."""

from __future__ import annotations

from dataclasses import dataclass

from outreachos_backend.rendering.geometry import CANVAS_HEIGHT, CANVAS_WIDTH, OUTPUT_FPS
from outreachos_backend.rendering.graph import GraphContext, GraphStep, render_graph
from outreachos_backend.rendering.steps import (
    AlphaCompositeStep,
    AlphaFadeStep,
    AlphaMergeStep,
    BleedPadStep,
    FocalCropStep,
    FpsStep,
    OverlayStep,
    ScalePadStep,
    TpadStep,
)

__all__ = ["AlphaGraphPlan", "VideoGraphPlan", "build_alpha_graph", "build_video_graph"]

SILENCE_SOURCE = "anullsrc=r=48000:cl=stereo"


@dataclass(frozen=True)
class VideoGraphPlan:
    ctx: GraphContext
    filter_complex: str
    video_label: str
    steps: tuple[str, ...]
    input_args: tuple[str, ...]
    audio_map: str


@dataclass(frozen=True)
class AlphaGraphPlan:
    ctx: GraphContext
    filter_complex: str
    video_label: str
    steps: tuple[str, ...]
    input_args: tuple[str, ...]
    audio_map: str


def _apply(ctx: GraphContext, current: str, steps: list[GraphStep]) -> tuple[str, list[str]]:
    """Run steps in order, recording only those that actually added a node."""
    applied: list[str] = []
    for step in steps:
        next_label = step.apply(ctx, current)
        if next_label != current:
            applied.append(step.step_id)
        current = next_label
    return current, applied


def build_video_graph(
    *,
    recording_input: str,
    alpha_input: str,
    trim_start_s: float,
    trim_duration_s: float,
    source_width: int,
    source_height: int,
    target_frames: int,
    target_duration_s: float,
    overlay_x: int,
    overlay_y: int,
) -> VideoGraphPlan:
    ctx = GraphContext()
    rec_idx = ctx.add_input(
        recording_input,
        "-accurate_seek",
        "-ss",
        f"{trim_start_s}",
        "-t",
        f"{trim_duration_s}",
    )
    alpha_idx = ctx.add_input(alpha_input)

    pad_duration_s = max(0.0, target_duration_s - trim_duration_s)
    steps: list[GraphStep] = []
    if not (source_width == CANVAS_WIDTH and source_height == CANVAS_HEIGHT):
        steps.append(ScalePadStep(source_width, source_height))
    steps.extend(
        [
            FpsStep(),
            TpadStep(pad_duration_s),
            OverlayStep(f"{alpha_idx}:v", overlay_x, overlay_y),
        ]
    )
    current, applied = _apply(ctx, f"{rec_idx}:v", steps)

    filter_complex, video_label = render_graph(ctx, current)
    return VideoGraphPlan(
        ctx=ctx,
        filter_complex=filter_complex,
        video_label=video_label,
        steps=tuple(applied),
        input_args=tuple(ctx.input_args()),
        # Narration rides on the alpha clip; the recording's own audio is dropped.
        audio_map=f"{alpha_idx}:a?",
    )


def build_alpha_graph(
    *,
    talking_head_input: str,
    backdrop_input: str,
    mask_input: str,
    frame_input: str,
    trim_start_s: float,
    duration_s: float,
    has_audio: bool,
    box_width: int,
    box_height: int,
    bleed_width: int,
    bleed_height: int,
    inset_left: int,
    inset_top: int,
    focal_x: float,
    focal_y: float,
    fade_frames: int,
    total_frames: int,
) -> AlphaGraphPlan:
    ctx = GraphContext()
    th_idx = ctx.add_input(
        talking_head_input,
        "-accurate_seek",
        "-ss",
        f"{trim_start_s}",
        "-t",
        f"{duration_s}",
    )
    # -framerate matters: the image2 demuxer defaults to 25fps, so without it these
    # static layers enter a 30fps composite at the wrong rate and framesync resamples
    # them. That made the alpha clip differ run-to-run from identical inputs, which a
    # content-addressed cache entry must never do.
    still = ("-loop", "1", "-framerate", str(OUTPUT_FPS), "-t", f"{duration_s}")
    bd_idx = ctx.add_input(backdrop_input, *still)
    mk_idx = ctx.add_input(mask_input, *still)
    fr_idx = ctx.add_input(frame_input, *still)

    if has_audio:
        audio_map = f"{th_idx}:a"
    else:
        # Registered through the same list as every other input so the index is
        # derived rather than assumed — this used to be a hardcoded `-map 4:a`.
        silence_idx = ctx.add_input(SILENCE_SOURCE, "-f", "lavfi", "-t", f"{duration_s}")
        audio_map = f"{silence_idx}:a"

    steps: list[GraphStep] = [
        # Rate-normalise the head *before* it meets the still layers: alphamerge and
        # overlay pair their inputs through framesync, and pairing streams that are
        # still at their source rate makes the composite depend on arrival order.
        FpsStep(),
        FocalCropStep(box_width, box_height, focal_x, focal_y),
        BleedPadStep(bleed_width, bleed_height, inset_left, inset_top),
        AlphaMergeStep(f"{mk_idx}:v"),
        AlphaCompositeStep(f"{bd_idx}:v", f"{fr_idx}:v"),
        AlphaFadeStep(fade_frames, total_frames),
    ]
    current, applied = _apply(ctx, f"{th_idx}:v", steps)

    filter_complex, video_label = render_graph(ctx, current)
    return AlphaGraphPlan(
        ctx=ctx,
        filter_complex=filter_complex,
        video_label=video_label,
        steps=tuple(applied),
        input_args=tuple(ctx.input_args()),
        audio_map=audio_map,
    )
