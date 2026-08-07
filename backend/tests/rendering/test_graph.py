"""Graph structure tests — no rendering on this branch."""

from outreachos_backend.rendering.pipeline import build_alpha_graph, build_video_graph


def test_video_graph_step_order() -> None:
    plan = build_video_graph(
        recording_input="rec.mp4",
        alpha_input="alpha.mov",
        trim_start_s=0.0,
        trim_duration_s=5.0,
        source_width=1920,
        source_height=1080,
        target_frames=75,
        target_duration_s=2.5,
        overlay_x=-12,
        overlay_y=900,
    )
    # The recording is longer than the target, so there is nothing to pad and no
    # tpad node lands in the graph. plan.steps reports what was emitted, not what
    # was offered.
    assert plan.steps == ("fps", "overlay")
    assert "tpad" not in plan.filter_complex
    assert "overlay=-12:900" in plan.filter_complex
    assert "scale=" not in plan.filter_complex


def test_video_graph_pads_when_recording_is_shorter_than_target() -> None:
    plan = build_video_graph(
        recording_input="rec.mp4",
        alpha_input="alpha.mov",
        trim_start_s=0.0,
        trim_duration_s=1.0,
        source_width=1920,
        source_height=1080,
        target_frames=75,
        target_duration_s=2.5,
        overlay_x=0,
        overlay_y=0,
    )
    assert plan.steps == ("fps", "tpad", "overlay")
    assert "tpad=stop_mode=clone:stop_duration=1.500000" in plan.filter_complex


def test_video_graph_includes_scale_pad_when_needed() -> None:
    plan = build_video_graph(
        recording_input="rec.mp4",
        alpha_input="alpha.mov",
        trim_start_s=0.0,
        trim_duration_s=5.0,
        source_width=1440,
        source_height=1080,
        target_frames=75,
        target_duration_s=2.5,
        overlay_x=100,
        overlay_y=100,
    )
    assert plan.steps[0] == "scale_pad"
    assert "pad=1920:1080" in plan.filter_complex


def test_alpha_graph_includes_merge_composite_fade() -> None:
    plan = build_alpha_graph(
        talking_head_input="head.mp4",
        backdrop_input="bd.png",
        mask_input="mask.png",
        frame_input="frame.png",
        trim_start_s=0.0,
        duration_s=2.5,
        has_audio=True,
        box_width=320,
        box_height=320,
        inner_width=320,
        inner_height=320,
        padding=0,
        bleed_width=576,
        bleed_height=584,
        inset_left=48,
        inset_top=48,
        focal_x=0.5,
        focal_y=0.5,
        fade_frames=12,
        total_frames=75,
    )
    assert "alphamerge" in plan.filter_complex
    assert "pad=576:584" in plan.filter_complex
    assert "fade=t=in" in plan.filter_complex
    # Order matters: normalise the rate first so the crop and the fade both count
    # frames at the output rate, and pad the bleed box only after cropping to the
    # visible box (ADR-0008).
    assert list(plan.steps) == [
        "fps",
        "focal_crop",
        "bleed_pad",
        "alphamerge",
        "composite",
        "alpha_fade",
    ]


def test_alpha_graph_input_args_match_filtergraph_indices() -> None:
    """The -i list and the filtergraph's stream indices come from one registry."""
    plan = build_alpha_graph(
        talking_head_input="head.mp4",
        backdrop_input="bd.png",
        mask_input="mask.png",
        frame_input="frame.png",
        trim_start_s=1.5,
        duration_s=2.5,
        has_audio=True,
        box_width=320,
        box_height=320,
        inner_width=320,
        inner_height=320,
        padding=0,
        bleed_width=576,
        bleed_height=584,
        inset_left=48,
        inset_top=48,
        focal_x=0.5,
        focal_y=0.5,
        fade_frames=12,
        total_frames=75,
    )
    args = list(plan.input_args)
    sources = [args[i + 1] for i, tok in enumerate(args) if tok == "-i"]
    assert sources == ["head.mp4", "bd.png", "mask.png", "frame.png"]
    assert args[:5] == ["-accurate_seek", "-ss", "1.5", "-t", "2.5"]
    assert plan.audio_map == "0:a"
    # Stills are looped for the clip's duration.
    assert args.count("-loop") == 3


def test_alpha_graph_appends_silence_input_when_source_has_no_audio() -> None:
    """Regression: the silence input's index used to be hardcoded as `-map 4:a`."""
    plan = build_alpha_graph(
        talking_head_input="head.mp4",
        backdrop_input="bd.png",
        mask_input="mask.png",
        frame_input="frame.png",
        trim_start_s=0.0,
        duration_s=2.5,
        has_audio=False,
        box_width=320,
        box_height=320,
        inner_width=320,
        inner_height=320,
        padding=0,
        bleed_width=576,
        bleed_height=584,
        inset_left=48,
        inset_top=48,
        focal_x=0.5,
        focal_y=0.5,
        fade_frames=12,
        total_frames=75,
    )
    args = list(plan.input_args)
    sources = [args[i + 1] for i, tok in enumerate(args) if tok == "-i"]
    assert len(sources) == 5
    assert sources[-1].startswith("anullsrc")
    assert plan.audio_map == f"{len(sources) - 1}:a"
    assert "-f" in args and "lavfi" in args


def test_video_graph_input_args_and_audio_map() -> None:
    plan = build_video_graph(
        recording_input="rec.mp4",
        alpha_input="alpha.mov",
        trim_start_s=2.0,
        trim_duration_s=5.0,
        source_width=1920,
        source_height=1080,
        target_frames=75,
        target_duration_s=2.5,
        overlay_x=0,
        overlay_y=0,
    )
    args = list(plan.input_args)
    sources = [args[i + 1] for i, tok in enumerate(args) if tok == "-i"]
    assert sources == ["rec.mp4", "alpha.mov"]
    assert args[:5] == ["-accurate_seek", "-ss", "2.0", "-t", "5.0"]
    # Narration comes from the alpha clip (index 1), not the recording.
    assert plan.audio_map == "1:a?"


def test_alpha_graph_pads_inner_crop_when_padding_set() -> None:
    plan = build_alpha_graph(
        talking_head_input="head.mp4",
        backdrop_input="bd.png",
        mask_input="mask.png",
        frame_input="frame.png",
        trim_start_s=0.0,
        duration_s=2.5,
        has_audio=True,
        box_width=320,
        box_height=320,
        inner_width=280,
        inner_height=280,
        padding=20,
        bleed_width=576,
        bleed_height=584,
        inset_left=48,
        inset_top=48,
        focal_x=0.5,
        focal_y=0.5,
        fade_frames=12,
        total_frames=75,
    )
    assert "scale=280:280" in plan.filter_complex
    assert "pad=320:320:20:20:color=0x00000000" in plan.filter_complex
    assert list(plan.steps) == [
        "fps",
        "focal_crop",
        "padding_pad",
        "bleed_pad",
        "alphamerge",
        "composite",
        "alpha_fade",
    ]


def test_alpha_fade_is_clamped_so_in_and_out_cannot_overlap() -> None:
    plan = build_alpha_graph(
        talking_head_input="head.mp4",
        backdrop_input="bd.png",
        mask_input="mask.png",
        frame_input="frame.png",
        trim_start_s=0.0,
        duration_s=0.1,
        has_audio=True,
        box_width=320,
        box_height=320,
        inner_width=320,
        inner_height=320,
        padding=0,
        bleed_width=576,
        bleed_height=584,
        inset_left=48,
        inset_top=48,
        focal_x=0.5,
        focal_y=0.5,
        fade_frames=12,
        total_frames=3,
    )
    # 3 frames cannot carry two 12-frame fades; they get one frame each.
    assert "fade=t=in:st=0:d=0.03333333333333333" in plan.filter_complex
