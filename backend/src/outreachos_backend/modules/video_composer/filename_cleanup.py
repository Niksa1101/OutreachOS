"""Derive a company name from a screen-recording filename.

PRD §P2: strip the extension, normalise separators, remove timestamps and
common noise words, then title-case the remainder. The rules live in the
backend; the frontend must not duplicate them.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["derive_company_name", "resolve_unique_company_name"]

# Longest phrases first so "screen recording" wins over bare "recording".
_NOISE_PHRASES: tuple[str, ...] = (
    "screen recording",
    "screen capture",
    "screen-recording",
    "screencast",
    "version 2",
    "version 1",
    "version 3",
    "recording",
    "capture",
    "final",
    "draft",
    "copy",
    "video",
    "v5",
    "v4",
    "v3",
    "v2",
    "v1",
)

_TIMESTAMP_PATTERN = re.compile(
    r"(?:"
    r"\d{4}[-_./]\d{2}[-_./]\d{2}(?:[-_ T]\d{2}[._:-]\d{2}(?:[._:-]\d{2})?)?"
    r"|(?<!\d)\d{8,14}(?!\d)"
    r")",
    re.IGNORECASE,
)
_SEPARATOR_PATTERN = re.compile(r"[_\-.+]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def derive_company_name(filename: str) -> str:
    """Return a title-cased company name derived from ``filename``."""
    stem = Path(filename).stem
    text = _TIMESTAMP_PATTERN.sub(" ", stem)
    text = _SEPARATOR_PATTERN.sub(" ", text)

    lowered = text.lower()
    for phrase in _NOISE_PHRASES:
        lowered = lowered.replace(phrase, " ")

    text = _WHITESPACE_PATTERN.sub(" ", lowered).strip()
    if not text:
        return "Untitled"
    return text.title()


def resolve_unique_company_name(base_name: str, taken: set[str]) -> str:
    """Return ``base_name`` or ``base_name (n)`` so it does not collide with ``taken``."""
    if base_name not in taken:
        return base_name

    suffix = 2
    while True:
        candidate = f"{base_name} ({suffix})"
        if candidate not in taken:
            return candidate
        suffix += 1
