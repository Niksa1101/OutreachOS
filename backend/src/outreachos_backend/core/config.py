"""Launch configuration and its precedence rules.

Q34 splits configuration by sensitivity:

- The **token** arrives on stdin, never argv or env. Any same-user process can
  read another's command line through WMI, and the environment is barely
  better. Q37 already holds stdin open for the process lifetime, so the channel
  was free.
- Everything else is a CLI argument, with ``pydantic-settings`` supplying env
  and ``.env`` overrides underneath.

Precedence is explicit and load-bearing: **CLI args > process env > ``.env``**.
A stale ``.env`` shadowing what Tauri passes at spawn is the "works in dev,
wrong in packaged" bug class this ordering exists to prevent.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["LaunchConfig", "LogLevel", "parse_launch_config"]

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_LOG_LEVELS: tuple[str, ...] = get_args(LogLevel)


class _EnvSettings(BaseSettings):
    """Env and ``.env`` layer. CLI arguments override anything here."""

    model_config = SettingsConfigDict(
        env_prefix="OOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = 0
    log_level: LogLevel = "INFO"


@dataclass(frozen=True)
class LaunchConfig:
    """Everything the process needs that did not arrive over stdin."""

    workspace: Path
    log_level: LogLevel
    dev: bool
    port: int
    """0 means "bind an ephemeral port", which is the normal case (ADR-0002)."""
    app_version: str | None
    """The Tauri shell's version. ``None`` when run standalone via
    ``pnpm dev:backend``, where there is no shell to report one — Q126."""

    take_over: bool
    """Q83's "Take over". Only ever set from the diagnostics screen's button."""
    ffmpeg_dir: Path | None
    """Q98: the *directory*, not the executable. P1 needs ``ffprobe.exe`` too,
    and one argument beats two that can disagree. Unused until P1."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="outreachos-backend",
        description="OutreachOS local backend. Normally spawned by the Tauri shell.",
    )
    parser.add_argument(
        "--workspace",
        required=True,
        type=Path,
        help="The user-chosen workspace directory. Q13: the sidecar is never "
        "spawned without one, so this has no default and no absent case.",
    )
    parser.add_argument(
        "--log-level",
        choices=_LOG_LEVELS,
        default=None,
        help="Overrides the level implied by --dev, in either direction.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Enables the %%TEMP%% token file, /docs and /openapi.json, and the "
        "localhost CORS origins. Derived from cfg!(debug_assertions) in Rust.",
    )
    parser.add_argument("--app-version", default=None, help="The Tauri shell's version.")
    parser.add_argument(
        "--take-over",
        action="store_true",
        help="Claim the workspace even if .oos-lock names a live-looking holder. "
        "Set only when the user has pressed the button (Q83) — we cannot tell a "
        "live instance on another machine from a crashed one, so this is a "
        "decision rather than a heuristic.",
    )
    parser.add_argument(
        "--ffmpeg-dir",
        type=Path,
        default=None,
        help="Directory containing ffmpeg.exe and ffprobe.exe. Unused until P1.",
    )
    return parser


def parse_launch_config(argv: list[str] | None = None) -> LaunchConfig:
    args = _build_parser().parse_args(argv)
    env = _EnvSettings()

    # Q57: --dev sets the *default* level to DEBUG; --log-level overrides that
    # default in either direction. The three sources compose rather than
    # conflict, and `model_fields_set` is what distinguishes "the env said
    # INFO" from "nobody said anything and INFO is the default".
    if args.log_level is not None:
        log_level: LogLevel = args.log_level
    elif "log_level" in env.model_fields_set:
        log_level = env.log_level
    else:
        log_level = "DEBUG" if args.dev else "INFO"

    return LaunchConfig(
        workspace=args.workspace,
        log_level=log_level,
        dev=bool(args.dev),
        port=env.port,
        app_version=args.app_version,
        take_over=bool(args.take_over),
        ffmpeg_dir=args.ffmpeg_dir,
    )
