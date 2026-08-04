"""Launch configuration precedence.

Q34: **CLI args > process env > `.env`**. The ordering is not a preference. A
stale `.env` shadowing what Tauri passes at spawn is the "works in dev, wrong
in packaged" bug class, and it is silent — the app runs, just against the wrong
workspace or at the wrong verbosity.
"""

from pathlib import Path

import pytest

from outreachos_backend.core.config import parse_launch_config


def base_args(*extra: str) -> list[str]:
    return ["--workspace", "C:/ws", *extra]


def test_workspace_is_required() -> None:
    # Q13's invariant: the sidecar is never spawned without a workspace, so
    # there is no default and no absent case to handle downstream.
    with pytest.raises(SystemExit):
        parse_launch_config([])


def test_dev_defaults_the_level_to_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OOS_LOG_LEVEL", raising=False)
    assert parse_launch_config(base_args("--dev")).log_level == "DEBUG"


def test_a_release_build_defaults_the_level_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OOS_LOG_LEVEL", raising=False)
    assert parse_launch_config(base_args()).log_level == "INFO"


def test_an_explicit_level_overrides_the_dev_default_downwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Q57: "--log-level overrides that default **in either direction**". A dev
    # build that wants quiet has to be able to ask for it.
    monkeypatch.delenv("OOS_LOG_LEVEL", raising=False)
    config = parse_launch_config(base_args("--dev", "--log-level", "WARNING"))
    assert config.log_level == "WARNING"


def test_an_explicit_level_overrides_the_release_default_upwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Q57 again: an advanced user debugging a packaged build should get a
    # verbose log — and only that, never a live OpenAPI surface.
    config = parse_launch_config(base_args("--log-level", "DEBUG"))
    assert config.log_level == "DEBUG"
    assert config.dev is False


def test_the_environment_beats_the_built_in_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OOS_LOG_LEVEL", "ERROR")
    assert parse_launch_config(base_args()).log_level == "ERROR"


def test_a_cli_argument_beats_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # The load-bearing case. This is the assertion that stops a leftover
    # `.env` from quietly winning over what Rust passed at spawn.
    monkeypatch.setenv("OOS_LOG_LEVEL", "ERROR")
    assert parse_launch_config(base_args("--log-level", "DEBUG")).log_level == "DEBUG"


def test_an_invalid_level_is_refused_rather_than_coerced() -> None:
    with pytest.raises(SystemExit):
        parse_launch_config(base_args("--log-level", "VERBOSE"))


def test_the_port_defaults_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    # ADR-0002: 0 means "bind an ephemeral port and report what you got",
    # which is the whole reason port selection moved to Python.
    monkeypatch.delenv("OOS_PORT", raising=False)
    assert parse_launch_config(base_args()).port == 0


def test_the_port_can_be_pinned_through_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OOS_PORT", "8756")
    assert parse_launch_config(base_args()).port == 8756


def test_the_ffmpeg_directory_is_a_directory_not_an_executable() -> None:
    # Q98: P1 needs ffprobe.exe as well as ffmpeg.exe, and one argument beats
    # two that can disagree about which build they came from.
    config = parse_launch_config(base_args("--ffmpeg-dir", "C:/vendor/ffmpeg"))
    assert config.ffmpeg_dir == Path("C:/vendor/ffmpeg")


def test_the_app_version_is_absent_when_run_standalone() -> None:
    # Q126: `pnpm dev:backend` has no Rust in the picture to supply one, and
    # reporting a literal "unknown" in the field you would ask a user to read
    # back is worse than reporting nothing.
    assert parse_launch_config(base_args()).app_version is None
