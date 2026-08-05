"""Headless render CLI — probe, caps, build-alpha, render, bench."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from pydantic import ValidationError

from outreachos_backend.rendering.alpha import build_alpha_clip
from outreachos_backend.rendering.binaries import resolve_binaries
from outreachos_backend.rendering.cache import CacheLayout
from outreachos_backend.rendering.capabilities import detect_encoders
from outreachos_backend.rendering.config import RenderBatchConfig
from outreachos_backend.rendering.errors import (
    RenderError,
    RenderUsageError,
)
from outreachos_backend.rendering.probe import probe_media
from outreachos_backend.rendering.process import register_shutdown_hook
from outreachos_backend.rendering.render import render_batch

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    register_shutdown_hook()
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.command is None:
        parser.print_help()
        return 2

    try:
        if args.command == "probe":
            return _cmd_probe(args)
        if args.command == "caps":
            return _cmd_caps(args)
        if args.command == "build-alpha":
            return _cmd_build_alpha(args)
        if args.command == "render":
            return _cmd_render(args)
        if args.command == "bench":
            return _cmd_bench(args)
    except RenderUsageError as exc:
        print(exc, file=sys.stderr)
        return 2
    except RenderError as exc:
        print(str(exc), file=sys.stderr)
        # RenderProcessError carries FFmpeg's own diagnostics; the message alone is
        # rarely enough to act on. Already capped per ADR-0011 at construction.
        detail = getattr(exc, "stderr", "")
        if detail:
            print(detail, file=sys.stderr)
        return 1

    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="outreachos-render")
    parser.add_argument(
        "--ffmpeg-dir",
        type=Path,
        default=_default_ffmpeg_dir(),
        help="Directory containing ffmpeg.exe and ffprobe.exe",
    )
    sub = parser.add_subparsers(dest="command")

    probe = sub.add_parser("probe", help="Probe a media file")
    probe.add_argument("path", type=Path)

    sub.add_parser("caps", help="Detect available H.264 encoders")

    build_alpha = sub.add_parser("build-alpha", help="Build or reuse cached alpha clip")
    build_alpha.add_argument("--config", type=Path, required=True)
    build_alpha.add_argument("--cache-dir", type=Path, default=None)
    build_alpha.add_argument("--out", type=Path, default=Path("./out"))
    build_alpha.add_argument("--dry-run", action="store_true")

    render = sub.add_parser("render", help="Render a batch from JSON config")
    render.add_argument("--config", type=Path, required=True)
    render.add_argument("--out", type=Path, default=Path("./out"))
    render.add_argument("--cache-dir", type=Path, default=None)
    render.add_argument("--dry-run", action="store_true")
    render.add_argument("--force-libx264", action="store_true")
    render.add_argument(
        "--strict-version",
        action="store_true",
        help="Fail instead of warn when the FFmpeg build is not the pinned one (ADR-0009)",
    )

    bench = sub.add_parser("bench", help="Benchmark cold vs warm cache")
    bench.add_argument("--config", type=Path, required=True)
    bench.add_argument("--out", type=Path, default=Path("./out"))
    bench.add_argument("--cache-dir", type=Path, default=None)
    bench.add_argument(
        "--markdown",
        type=Path,
        default=None,
        metavar="FILE",
        help="Append the result row to this Markdown file (e.g. docs/p1-verification.md)",
    )
    bench.add_argument("--videos", type=int, default=8)

    return parser


def _default_ffmpeg_dir() -> Path | None:
    repo = Path(__file__).resolve().parents[4]
    candidate = repo / "vendor" / "ffmpeg"
    return candidate if candidate.is_dir() else None


def _load_config(path: Path) -> RenderBatchConfig:
    """Config problems are usage errors (exit 2), not tracebacks."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RenderUsageError(f"Cannot read config {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RenderUsageError(f"Invalid JSON in {path}: {exc}") from exc
    try:
        return RenderBatchConfig.model_validate(payload)
    except ValidationError as exc:
        raise RenderUsageError(f"Invalid config {path}:\n{exc}") from exc


def _cache_layout(args: argparse.Namespace) -> CacheLayout:
    cache_root = args.cache_dir or (args.out / ".outreachos-cache")
    return CacheLayout(root=cache_root)


def _cmd_probe(args: argparse.Namespace) -> int:
    binaries = resolve_binaries(args.ffmpeg_dir)
    result = probe_media(binaries, str(args.path))
    print(result.model_dump_json(indent=2))
    return 0


def _cmd_caps(args: argparse.Namespace) -> int:
    binaries = resolve_binaries(args.ffmpeg_dir)
    encoders = detect_encoders(binaries)
    print(json.dumps({"encoders": encoders, "version": binaries.version_line}, indent=2))
    return 0


def _cmd_build_alpha(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    binaries = resolve_binaries(args.ffmpeg_dir)
    layout = _cache_layout(args)
    result = build_alpha_clip(binaries, config, layout, dry_run=args.dry_run)
    print(
        json.dumps(
            {
                "alpha_key": result.alpha_key,
                "assets_key": result.assets_key,
                "clip": str(result.clip_path),
                "frames": result.frame_count,
                "cache_hit": result.cache_hit,
            },
            indent=2,
        )
    )
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    strict = _strict_version(args)
    binaries = resolve_binaries(args.ffmpeg_dir, strict_version=strict)
    layout = _cache_layout(args)

    alpha = build_alpha_clip(binaries, config, layout, dry_run=args.dry_run)
    results = render_batch(
        binaries,
        config,
        alpha,
        args.out,
        dry_run=args.dry_run,
        force_libx264=args.force_libx264 or strict,
        # Strict mode is the reproducible-output mode (ADR-0009), so it pins
        # threading too; ordinary renders keep libx264's default.
        deterministic=strict,
    )
    failed = [r for r in results if not r.ok]
    for result in results:
        status = "ok" if result.ok else "failed"
        print(f"{status}: {result.output_path or result.error}")
        for warning in result.warnings:
            print(f"  warning [{warning.code}]: {warning.message}")
    return 1 if failed else 0


def _cmd_bench(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    config = config.model_copy(update={"recordings": config.recordings[: args.videos]})
    binaries = resolve_binaries(args.ffmpeg_dir)
    layout = _cache_layout(args)

    # The cold pass needs an empty cache, but --cache-dir is a caller-supplied path:
    # wiping it would be deleting a directory we were only given to read and write
    # entries under. Use a scratch cache for cold, the real one for warm.
    with tempfile.TemporaryDirectory(prefix="outreachos-bench-") as scratch:
        cold_layout = CacheLayout(root=Path(scratch))
        cold_start = time.perf_counter()
        alpha = build_alpha_clip(binaries, config, cold_layout)
        render_batch(binaries, config, alpha, args.out, force_libx264=True)
        cold_s = time.perf_counter() - cold_start

    # Prime the real cache, then measure the hit.
    build_alpha_clip(binaries, config, layout)
    warm_start = time.perf_counter()
    alpha = build_alpha_clip(binaries, config, layout)
    render_batch(binaries, config, alpha, args.out, force_libx264=True)
    warm_s = time.perf_counter() - warm_start

    row = (
        f"| {len(config.recordings)} videos | {cold_s:.2f}s | {warm_s:.2f}s | "
        f"{binaries.version_line.split()[2]} |"
    )
    print(row)
    if args.markdown is not None:
        # An explicit destination rather than one derived from __file__: the package
        # is importable from site-packages, where no repo layout exists to walk up to.
        doc: Path = args.markdown
        if not doc.is_file():
            raise RenderUsageError(f"--markdown target does not exist: {doc}")
        with doc.open("a", encoding="utf-8") as handle:
            handle.write(row + "\n")
    return 0


def _strict_version(args: argparse.Namespace) -> bool:
    """ADR-0009's determinism guarantee is only worth anything if the pin is enforced.

    Env var as well as flag so the golden suite and CI can turn it on without
    threading an argument through every invocation.
    """
    return bool(getattr(args, "strict_version", False)) or os.environ.get(
        "OOS_RENDER_STRICT", ""
    ).strip().lower() in ("1", "true", "yes")


if __name__ == "__main__":
    raise SystemExit(main())
