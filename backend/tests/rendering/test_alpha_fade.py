"""Unit coverage for AlphaFadeStep — the fade-duration bug fixed in ticket 12.

Previously `alpha.py` halved the configured duration before handing it to this
step (`duration_ms / 1000 * fps / 2`), so a 500ms setting produced a ~250ms
fade-in and ~250ms fade-out. The fix applies the full configured duration to
*each* edge; this step's own clamp (`total_frames // 2`) is what prevents the
two fades from overlapping on a short clip, unchanged by that fix.
"""

from outreachos_backend.rendering.graph import GraphContext
from outreachos_backend.rendering.steps.alpha_fade import AlphaFadeStep


def test_fade_frames_unclamped_when_clip_is_long_enough() -> None:
    step = AlphaFadeStep(fade_frames=15, total_frames=750)
    assert step.fade_frames == 15


def test_fade_frames_clamped_to_half_the_clip_when_too_short() -> None:
    step = AlphaFadeStep(fade_frames=15, total_frames=20)
    assert step.fade_frames == 10


def test_zero_fade_frames_is_a_no_op() -> None:
    """Finding E5: `animation.duration_ms: 0` means no fade at all, not a
    forced one-frame fade — `apply` must not add a filter node."""
    step = AlphaFadeStep(fade_frames=0, total_frames=750)
    assert step.fade_frames == 0

    ctx = GraphContext()
    out = step.apply(ctx, "in0")

    assert out == "in0"
    assert ctx.nodes == []
