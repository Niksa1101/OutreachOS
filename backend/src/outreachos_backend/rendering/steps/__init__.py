"""Composite step objects.

Each step contributes nodes to a single FFmpeg filtergraph. The pipeline is an
ordered list of these rather than a hardcoded command string, precisely so that
deferred features — text layers above all — slot in additively instead of
forcing a restructure.

P1 assembles: trim -> scale/pad -> fps -> tpad -> overlay -> encode.
"""
