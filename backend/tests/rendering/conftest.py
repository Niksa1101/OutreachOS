"""Shared FFmpeg fixtures for render tests.

Sources are generated with lavfi rather than committed as binaries: generation is
itself pinned by the FFmpeg version (ADR-0009), and it keeps media blobs out of git.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.process import run_tool

REPO_ROOT = Path(__file__).resolve().parents[3]
FFMPEG_DIR = REPO_ROOT / "vendor" / "ffmpeg"
GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "golden"

# Every frame of the ramp has a distinct, known luma, so a trim can be verified
# numerically instead of against a picture. The base and step keep the whole ramp
# inside limited-range luma (16..235): past 235 the frames clip to white on the
# YUV->RGB conversion and become indistinguishable from each other.
GRAY_RAMP_BASE = 16
GRAY_RAMP_STEP = 2
GRAY_RAMP_FRAMES = 90


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Rewrite golden reference images instead of asserting against them.",
    )


@pytest.fixture(scope="session")
def update_golden(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--update-golden"))


@pytest.fixture(scope="session")
def ffmpeg_dir() -> Path:
    if not (FFMPEG_DIR / "ffmpeg.exe").is_file():
        pytest.skip("vendor/ffmpeg not present — run scripts/fetch-ffmpeg.ps1")
    return FFMPEG_DIR


@pytest.fixture(scope="session")
def ffmpeg_binaries(ffmpeg_dir: Path) -> Binaries:
    from outreachos_backend.rendering.binaries import resolve_binaries

    return resolve_binaries(ffmpeg_dir)


@pytest.fixture(scope="session")
def render_fixtures(tmp_path_factory: pytest.TempPathFactory, ffmpeg_dir: Path) -> Path:
    root = tmp_path_factory.mktemp("render_fixtures")
    _ensure_fixtures(root, ffmpeg_dir)
    return root


# Fixtures are regenerated into a fresh tmp dir every session, so they must encode
# reproducibly or the golden references drift between runs: libx264's default thread
# count derives from core count and changes the bitstream (ADR-0009).
X264_DETERMINISTIC = ["-threads", "1", "-x264-params", "sliced-threads=0"]

# Matroska stamps a random SegmentUID and a writing date into every file; without
# bitexact the VFR fixture differs on every run even though its frames do not.
BITEXACT = ["-fflags", "+bitexact", "-flags:v", "+bitexact"]


def _run_ffmpeg(ffmpeg: Path, args: list[str]) -> None:
    run_tool(
        [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", *BITEXACT, *args],
        timeout_s=300.0,
    )


def _ensure_fixtures(root: Path, ffmpeg_dir: Path) -> None:
    ffmpeg = ffmpeg_dir / "ffmpeg.exe"

    _make_talking_head(ffmpeg, root / "talking_head.mp4")
    _make_screen(ffmpeg, root / "screen_1080p.mp4", "1920x1080", duration=5, audio=True)
    _make_screen(ffmpeg, root / "screen_4_3.mp4", "1440x1080", duration=4, audio=False)
    _make_screen(ffmpeg, root / "screen_21_9.mp4", "2560x1080", duration=4, audio=False)
    _make_screen(ffmpeg, root / "screen_no_audio.mp4", "1920x1080", duration=4, audio=False)
    _make_screen(ffmpeg, root / "screen_long.mp4", "1920x1080", duration=12, audio=True)
    _make_gray_ramp(ffmpeg, root / "gray_ramp.mp4")
    _make_vfr(ffmpeg, root / "screen_vfr.mkv")
    _make_rotated(ffmpeg, root / "screen_rotated.mp4")

    _write_batch(root)


def _make_talking_head(ffmpeg: Path, path: Path) -> None:
    if path.exists():
        return
    _run_ffmpeg(
        ffmpeg,
        [
            "-f", "lavfi", "-i", "testsrc=duration=3:size=640x640:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "libx264", *X264_DETERMINISTIC, "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(path),
        ],
    )  # fmt: skip


def _make_screen(ffmpeg: Path, path: Path, size: str, *, duration: int, audio: bool) -> None:
    if path.exists():
        return
    args = ["-f", "lavfi", "-i", f"testsrc2=duration={duration}:size={size}:rate=30"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=880:duration={duration}", "-c:a", "aac"]
    else:
        args += ["-an"]
    args += ["-c:v", "libx264", *X264_DETERMINISTIC, "-pix_fmt", "yuv420p", str(path)]
    _run_ffmpeg(ffmpeg, args)


def _make_gray_ramp(ffmpeg: Path, path: Path) -> None:
    """Frame N is a flat grey of luma BASE + N*STEP, encoded losslessly."""
    if path.exists():
        return
    _run_ffmpeg(
        ffmpeg,
        [
            "-f", "lavfi",
            "-i", f"color=c=black:s=1920x1080:r=30:d={GRAY_RAMP_FRAMES / 30}",
            "-vf", f"geq=lum='{GRAY_RAMP_BASE}+N*{GRAY_RAMP_STEP}':cb=128:cr=128",
            "-c:v", "libx264", *X264_DETERMINISTIC, "-qp", "0", "-pix_fmt", "yuv420p", "-an",
            "-frames:v", str(GRAY_RAMP_FRAMES),
            str(path),
        ],
    )  # fmt: skip


def _make_vfr(ffmpeg: Path, path: Path) -> None:
    """Uneven frame timestamps, so `fps=30` has real work to do."""
    if path.exists():
        return
    _run_ffmpeg(
        ffmpeg,
        [
            "-f", "lavfi", "-i", "testsrc2=duration=5:size=1920x1080:rate=60",
            "-vf", "select='not(mod(n,3))+not(mod(n,7))',setpts=N/(20*TB)",
            "-fps_mode", "vfr", "-c:v", "libx264", *X264_DETERMINISTIC,
            "-pix_fmt", "yuv420p", "-an",
            str(path),
        ],
    )  # fmt: skip


def _make_rotated(ffmpeg: Path, path: Path) -> None:
    """Portrait frames carrying a 90° display matrix — probes as 1920x1080."""
    if path.exists():
        return
    portrait = path.with_name("_rotated_src.mp4")
    if not portrait.exists():
        _run_ffmpeg(
            ffmpeg,
            [
                "-f", "lavfi", "-i", "testsrc2=duration=4:size=1080x1920:rate=30",
                "-c:v", "libx264", *X264_DETERMINISTIC, "-pix_fmt", "yuv420p", "-an",
                str(portrait),
            ],
        )  # fmt: skip
    _run_ffmpeg(ffmpeg, ["-display_rotation", "90", "-i", str(portrait), "-c", "copy", str(path)])


def _write_batch(root: Path) -> None:
    batch = {
        "talking_head": {
            "source_path": str(root / "talking_head.mp4"),
            "trim_start_ms": 0,
            "trim_end_ms": 2500,
            "focal_x": 0.5,
            "focal_y": 0.5,
        },
        "overlay": {
            "schema_version": 1,
            "anchor": "bottom_right",
            "size": {"width": 320, "height": 320},
            "offset": {"x": 48, "y": 48},
            "shape": "circle",
            "border_radius": 24,
            "opacity": 1.0,
            "padding": 0,
            "border": {"enabled": True, "width": 4, "color": "#FFFFFF"},
            "shadow": {
                "enabled": True,
                "blur": 24,
                "offset_x": 0,
                "offset_y": 8,
                "opacity": 0.45,
                "color": "#000000",
            },
            "background": {"enabled": False, "color": "#0A0A0A"},
            "animation": {"type": "fade", "duration_ms": 400},
        },
        "recordings": [
            {"source_path": str(root / "screen_1080p.mp4"), "output_basename": "baseline"},
            {"source_path": str(root / "screen_4_3.mp4"), "output_basename": "aspect_4_3"},
            {"source_path": str(root / "screen_no_audio.mp4"), "output_basename": "no_audio"},
        ],
        "quality": "draft",
        "encoder": "libx264",
        "owner_ref": "test-batch",
        "owner_kind": "test",
    }
    (root / "batch.json").write_text(json.dumps(batch, indent=2), encoding="utf-8")
