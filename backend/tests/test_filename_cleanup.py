"""Filename cleanup rules for screen-recording imports."""

import pytest

from outreachos_backend.modules.video_composer.filename_cleanup import (
    derive_company_name,
    resolve_unique_company_name,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("acme-corp_demo.mp4", "Acme Corp Demo"),
        ("ACME_CORP.mp4", "Acme Corp"),
        ("stripe.com walkthrough.mov", "Stripe Com Walkthrough"),
        ("notion_final_v2.mp4", "Notion"),
        ("figma screen recording 2024-03-15 14.30.22.mp4", "Figma"),
        ("linear_screen_capture_20240315.mp4", "Linear"),
        ("hubspot copy.mp4", "Hubspot"),
        ("untitled screen recording.mp4", "Untitled"),
        ("20250301_demo.mp4", "Demo"),
    ],
)
def test_derive_company_name(filename: str, expected: str) -> None:
    assert derive_company_name(filename) == expected


def test_resolve_unique_company_name_adds_suffixes() -> None:
    taken = {"Acme Corp"}
    assert resolve_unique_company_name("Acme Corp", taken) == "Acme Corp (2)"
    taken.add("Acme Corp (2)")
    assert resolve_unique_company_name("Acme Corp", taken) == "Acme Corp (3)"


def test_resolve_unique_company_name_keeps_first_name() -> None:
    taken: set[str] = set()
    assert resolve_unique_company_name("Acme Corp", taken) == "Acme Corp"
