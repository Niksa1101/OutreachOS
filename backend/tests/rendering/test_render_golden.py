"""Golden-frame render integration tests.

Nine cases, one per row of docs/p1-verification.md. References are stored at half
resolution: full-res PNGs would add tens of MB to the repo, and a 960x540 comparison
still catches placement drift of a pixel or two at output scale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image

from outreachos_backend.rendering.alpha import AlphaBuildResult, build_alpha_clip
from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.cache import CacheLayout
from outreachos_backend.rendering.config import RenderBatchConfig, ScreenRecordingJob
from outreachos_backend.rendering.geometry import OUTPUT_FPS, compute_geometry
from outreachos_backend.rendering.process import run_tool
from outreachos_backend.rendering.render import JobResult, render_batch, render_one

from .conftest import GOLDEN_DIR

REFERENCE_SIZE = (960, 540)


@dataclass(frozen=True)
class GoldenCase:
    name: str
    source: str
    trim_start_ms: int = 0
    trim_end_ms: int | None = None
    expect_warning: str | None = None


CASES: list[GoldenCase] = [
    GoldenCase("baseline", "screen_1080p.mp4"),
    GoldenCase("aspect_4_3", "screen_4_3.mp4"),
    GoldenCase("aspect_21_9", "screen_21_9.mp4"),
    GoldenCase("no_audio", "screen_no_audio.mp4"),
    GoldenCase(
        "short_recording",
        "screen_4_3.mp4",
        trim_end_ms=500,
        expect_warning="recording_shorter_than_talking_head",
    ),
    GoldenCase("long_recording", "screen_long.mp4"),
    GoldenCase("frame_accurate_trim", "gray_ramp.mp4", trim_start_ms=1000),
    GoldenCase("vfr_source", "screen_vfr.mkv"),
    GoldenCase("rotated_source", "screen_rotated.mp4"),
]


# --------------------------------------------------------------------------
# Comparison helpers
# --------------------------------------------------------------------------


def _decode_frame(ffmpeg: Path, video: Path, frame_index: int, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_tool(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            f"select=eq(n\\,{frame_index})",
            "-vframes",
            "1",
            "-pix_fmt",
            "rgb24",
            # ADR-0009: golden decodes pin swscale so the comparison measures the
            # encode rather than the scaler's defaults.
            "-sws_flags",
            "full_chroma_int+accurate_rnd",
            str(dest),
        ],
        timeout_s=120.0,
    )


def _compare_images(a: Path, b: Path, *, max_delta: int = 2, max_mae: float = 0.5) -> None:
    img_a = Image.open(a).convert("RGB")
    img_b = Image.open(b).convert("RGB")
    assert img_a.size == img_b.size, f"{img_a.size} != {img_b.size}"
    pixels_a = list(img_a.getdata())
    pixels_b = list(img_b.getdata())
    deltas = [
        max(abs(c1 - c2) for c1, c2 in zip(p1, p2, strict=True))
        for p1, p2 in zip(pixels_a, pixels_b, strict=True)
    ]
    mae = sum(
        sum(abs(c1 - c2) for c1, c2 in zip(p1, p2, strict=True))
        for p1, p2 in zip(pixels_a, pixels_b, strict=True)
    ) / (len(pixels_a) * 3)
    assert max(deltas) <= max_delta, f"max delta {max(deltas)} > {max_delta}"
    assert mae <= max_mae, f"MAE {mae} > {max_mae}"


def _assert_golden(actual_png: Path, reference: Path, *, update: bool) -> None:
    scaled = actual_png.with_name(f"{actual_png.stem}_scaled.png")
    Image.open(actual_png).convert("RGB").resize(REFERENCE_SIZE, Image.Resampling.LANCZOS).save(
        scaled
    )
    if update:
        reference.parent.mkdir(parents=True, exist_ok=True)
        Image.open(scaled).save(reference)
        return
    # A missing reference must fail, not silently self-heal: an auto-generated
    # baseline turns a regression test into a no-op.
    assert reference.is_file(), (
        f"Missing golden reference {reference.name}. Run "
        f"`pytest -m render --update-golden` and review the result before committing."
    )
    _compare_images(scaled, reference)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_config(render_fixtures: Path) -> RenderBatchConfig:
    return RenderBatchConfig.model_validate(
        json.loads((render_fixtures / "batch.json").read_text(encoding="utf-8"))
    )


@pytest.fixture(scope="session")
def golden_alpha(
    ffmpeg_binaries: Binaries,
    base_config: RenderBatchConfig,
    tmp_path_factory: pytest.TempPathFactory,
) -> AlphaBuildResult:
    """One alpha clip for the whole suite — it is identical across cases."""
    layout = CacheLayout(root=tmp_path_factory.mktemp("golden_cache"))
    return build_alpha_clip(ffmpeg_binaries, base_config, layout)


def _render_case(
    binaries: Binaries,
    base_config: RenderBatchConfig,
    alpha: AlphaBuildResult,
    case: GoldenCase,
    fixtures: Path,
    out_dir: Path,
) -> JobResult:
    job = ScreenRecordingJob(
        source_path=fixtures / case.source,
        output_basename=case.name,
        trim_start_ms=case.trim_start_ms,
        trim_end_ms=case.trim_end_ms,
    )
    config = base_config.model_copy(update={"recordings": [job]})
    return render_one(
        binaries,
        config,
        alpha,
        job,
        out_dir,
        encoder="libx264",
        force_libx264=True,
        deterministic=True,
    )


def _assert_frame_count(binaries: Binaries, path: Path, expected: int) -> None:
    stdout = run_tool(
        [
            str(binaries.ffprobe),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "json",
            str(path),
        ],
        timeout_s=120.0,
    )
    actual = int(json.loads(stdout)["streams"][0]["nb_read_frames"])
    assert actual == expected, f"{path.name}: {actual} frames, expected {expected}"


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


@pytest.mark.render
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_golden_case(
    case: GoldenCase,
    ffmpeg_binaries: Binaries,
    base_config: RenderBatchConfig,
    golden_alpha: AlphaBuildResult,
    render_fixtures: Path,
    tmp_path: Path,
    update_golden: bool,
) -> None:
    result = _render_case(
        ffmpeg_binaries, base_config, golden_alpha, case, render_fixtures, tmp_path / "out"
    )

    assert result.ok, result.error
    assert result.output_path is not None
    assert result.output_path.stat().st_size > 0

    if case.expect_warning:
        codes = [w.code for w in result.warnings]
        assert case.expect_warning in codes, f"expected {case.expect_warning}, got {codes}"

    # Every case is cut to the talking head's length, whatever the source ran for.
    _assert_frame_count(ffmpeg_binaries, result.output_path, golden_alpha.frame_count)

    for index in (0, golden_alpha.frame_count - 1):
        frame = tmp_path / f"{case.name}_{index}.png"
        _decode_frame(ffmpeg_binaries.ffmpeg, result.output_path, index, frame)
        _assert_golden(frame, GOLDEN_DIR / f"{case.name}_frame{index}.png", update=update_golden)


@dataclass(frozen=True)
class OverlayShapeCase:
    name: str
    overlay_overrides: dict[str, object]


OVERLAY_SHAPE_CASES: list[OverlayShapeCase] = [
    OverlayShapeCase("shape_rounded_rect", {"shape": "rounded_rect", "border_radius": 32}),
    OverlayShapeCase("shape_rect", {"shape": "rect"}),
    OverlayShapeCase("shape_circle_padded", {"padding": 24}),
    # Finding C1: opacity fades only the video mask — border/background/shadow
    # stay fully opaque. Pins that semantic on the render side.
    OverlayShapeCase("opacity_faded", {"opacity": 0.6}),
]


@pytest.mark.render
@pytest.mark.parametrize("case", OVERLAY_SHAPE_CASES, ids=lambda c: c.name)
def test_overlay_shape_and_padding_golden_frame(
    case: OverlayShapeCase,
    ffmpeg_binaries: Binaries,
    base_config: RenderBatchConfig,
    render_fixtures: Path,
    tmp_path: Path,
    update_golden: bool,
) -> None:
    """Ticket 12: preview and rendered output must agree within golden-frame
    tolerance for all three shapes, plus padding. The default `baseline` case
    already covers the circle shape at padding=0; this covers the other two
    shapes and one padded case.
    """
    overlay = base_config.overlay.model_copy(update=case.overlay_overrides)
    config = base_config.model_copy(update={"overlay": overlay})

    layout = CacheLayout(root=tmp_path / "cache")
    alpha = build_alpha_clip(ffmpeg_binaries, config, layout)

    job = ScreenRecordingJob(
        source_path=render_fixtures / "screen_1080p.mp4", output_basename=case.name
    )
    result = render_one(
        ffmpeg_binaries,
        config.model_copy(update={"recordings": [job]}),
        alpha,
        job,
        tmp_path / "out",
        encoder="libx264",
        force_libx264=True,
        deterministic=True,
    )
    assert result.ok, result.error
    assert result.output_path is not None

    frame_png = tmp_path / f"{case.name}.png"
    _decode_frame(ffmpeg_binaries.ffmpeg, result.output_path, alpha.frame_count // 2, frame_png)
    _assert_golden(frame_png, GOLDEN_DIR / f"{case.name}_frame.png", update=update_golden)


@pytest.mark.render
def test_overlay_lands_at_the_configured_offset(
    ffmpeg_binaries: Binaries,
    base_config: RenderBatchConfig,
    golden_alpha: AlphaBuildResult,
    render_fixtures: Path,
    tmp_path: Path,
) -> None:
    """End-to-end guard for ADR-0008: the overlay must sit 48px in, as configured.

    The geometry unit tests assert the maths; this asserts the maths survives the
    filtergraph, which is where anchoring the bleed box instead of the visible box
    actually showed up.
    """
    result = _render_case(
        ffmpeg_binaries,
        base_config,
        golden_alpha,
        GoldenCase("placement", "screen_1080p.mp4"),
        render_fixtures,
        tmp_path / "out",
    )
    assert result.ok, result.error
    assert result.output_path is not None

    # Mid-clip, past the fade-in, so the overlay is at full opacity.
    frame_png = tmp_path / "placement.png"
    _decode_frame(
        ffmpeg_binaries.ffmpeg, result.output_path, golden_alpha.frame_count // 2, frame_png
    )
    image = Image.open(frame_png).convert("RGB")

    geom = compute_geometry(base_config.overlay)
    box_right = geom.overlay_x + geom.bleed_insets.left + geom.box_width
    box_bottom = geom.overlay_y + geom.bleed_insets.top + geom.box_height
    assert image.width - box_right == 48
    assert image.height - box_bottom == 48

    # The circle's rightmost point sits on the box's vertical centre line, and the
    # border ring there is the brightest thing around.
    centre_y = geom.overlay_y + geom.bleed_insets.top + geom.box_height // 2
    edge = _brightest_x_near(image, centre_y, box_right)
    assert abs(edge - box_right) <= 6, f"overlay edge at x={edge}, expected near {box_right}"


def _brightest_x_near(image: Image.Image, y: int, expected_x: int, span: int = 40) -> int:
    lo = max(0, expected_x - span)
    hi = min(image.width, expected_x + span)
    row = [(sum(image.getpixel((x, y))), x) for x in range(lo, hi)]  # type: ignore[arg-type]
    return max(row)[1]


@pytest.mark.render
def test_frame_accurate_trim_lands_on_the_expected_ramp_frame(
    ffmpeg_binaries: Binaries,
    base_config: RenderBatchConfig,
    golden_alpha: AlphaBuildResult,
    render_fixtures: Path,
    tmp_path: Path,
) -> None:
    """The gray ramp encodes frame number as luma, so a trim is checkable as a number.

    Calibrated entirely against other renders of the same ramp rather than against
    the source file. Output is tagged bt709 while the lavfi source is untagged, so
    the same frame decodes to a different RGB value through each path (70.00 vs
    68.33) — comparing across the two measures the colour tag, not the trim.
    """
    trims = {
        ms: _ramp_level(ffmpeg_binaries, base_config, golden_alpha, render_fixtures, tmp_path, ms)
        for ms in (0, 1000, 2000)
    }

    # Two seconds is 60 frames, which calibrates RGB units per source frame.
    per_frame = (trims[2000] - trims[0]) / 60
    assert per_frame > 1.0, f"ramp has no usable resolution ({per_frame:.2f}/frame)"

    measured = (trims[1000] - trims[0]) / per_frame
    expected = 1000 / 1000 * OUTPUT_FPS
    assert abs(measured - expected) < 0.5, (
        f"a 1000ms trim landed on source frame {measured:.2f}, expected {expected:.0f} "
        f"(levels {trims}, {per_frame:.2f} RGB/frame)"
    )


def _ramp_level(
    binaries: Binaries,
    base_config: RenderBatchConfig,
    alpha: AlphaBuildResult,
    fixtures: Path,
    tmp_path: Path,
    trim_start_ms: int,
) -> float:
    """Mean level of output frame 0 for a ramp render trimmed at `trim_start_ms`."""
    case = GoldenCase(f"ramp_{trim_start_ms}", "gray_ramp.mp4", trim_start_ms=trim_start_ms)
    result = _render_case(binaries, base_config, alpha, case, fixtures, tmp_path / "out")
    assert result.ok, result.error
    assert result.output_path is not None
    png = tmp_path / f"ramp_{trim_start_ms}.png"
    _decode_frame(binaries.ffmpeg, result.output_path, 0, png)
    # Top-left corner, far from the bottom-right overlay.
    patch = list(Image.open(png).convert("RGB").crop((0, 0, 200, 200)).getdata())
    return sum(sum(p) for p in patch) / (len(patch) * 3)


@pytest.mark.render
def test_short_recording_freezes_last_frame(
    ffmpeg_binaries: Binaries,
    base_config: RenderBatchConfig,
    golden_alpha: AlphaBuildResult,
    render_fixtures: Path,
    tmp_path: Path,
) -> None:
    case = GoldenCase("short", "screen_4_3.mp4", trim_end_ms=500)
    result = _render_case(
        ffmpeg_binaries, base_config, golden_alpha, case, render_fixtures, tmp_path / "out"
    )
    assert result.ok, result.error
    assert result.output_path is not None
    assert "tpad=stop_mode=clone" in " ".join(result.command or [])

    last_png = tmp_path / "last.png"
    _decode_frame(
        ffmpeg_binaries.ffmpeg, result.output_path, golden_alpha.frame_count - 1, last_png
    )
    pixels = list(Image.open(last_png).convert("RGB").getdata())
    mean_luma = sum(sum(p) for p in pixels) / (len(pixels) * 3)
    assert mean_luma > 10, "last frame should be frozen content, not black"


@pytest.mark.render
def test_one_unreadable_source_does_not_abort_the_batch(
    ffmpeg_binaries: Binaries,
    base_config: RenderBatchConfig,
    golden_alpha: AlphaBuildResult,
    render_fixtures: Path,
    tmp_path: Path,
) -> None:
    """A corrupt recording fails its own job; the ones queued behind it still render."""
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"not a video" * 100)
    out_dir = tmp_path / "out"

    config = base_config.model_copy(
        update={
            "recordings": [
                ScreenRecordingJob(source_path=corrupt, output_basename="corrupt"),
                ScreenRecordingJob(
                    source_path=render_fixtures / "screen_1080p.mp4",
                    output_basename="good",
                ),
            ]
        }
    )
    results = render_batch(
        ffmpeg_binaries, config, golden_alpha, out_dir, force_libx264=True, deterministic=True
    )

    assert len(results) == 2
    assert not results[0].ok
    assert results[0].output_path is None
    assert results[1].ok, results[1].error
    assert results[1].output_path is not None and results[1].output_path.is_file()
    # The failed job leaves nothing half-written behind.
    assert [p.name for p in out_dir.glob("corrupt*")] == []


@pytest.mark.render
def test_probe_and_caps_smoke(ffmpeg_binaries: Binaries, render_fixtures: Path) -> None:
    from outreachos_backend.rendering.capabilities import detect_encoders
    from outreachos_backend.rendering.probe import probe_media

    probe = probe_media(ffmpeg_binaries, str(render_fixtures / "screen_1080p.mp4"))
    assert probe.width == 1920
    encoders = detect_encoders(ffmpeg_binaries)
    assert "libx264" in encoders
