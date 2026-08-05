from outreachos_backend.rendering.geometry import OUTPUT_FPS
from outreachos_backend.rendering.graph import FilterNode, GraphContext, GraphStep


class AlphaFadeStep(GraphStep):
    step_id = "alpha_fade"

    def __init__(self, fade_frames: int, total_frames: int) -> None:
        # Overlapping fades multiply, so a clip shorter than two fades would dim
        # overall and a very short one would never reach full opacity. Split the
        # available frames evenly instead.
        self.fade_frames = max(0, min(fade_frames, total_frames // 2))
        self.total_frames = total_frames

    def apply(self, ctx: GraphContext, current: str) -> str:
        if self.fade_frames <= 0:
            return current
        out = ctx.new_label("fade")
        fade_s = self.fade_frames / OUTPUT_FPS
        fade_out_start = max(0, self.total_frames - self.fade_frames) / OUTPUT_FPS
        ctx.add_node(
            FilterNode(
                id=self.step_id,
                filter=(
                    f"fade=t=in:st=0:d={fade_s}:alpha=1,"
                    f"fade=t=out:st={fade_out_start}:d={fade_s}:alpha=1"
                ),
                inputs=[current],
                outputs=[out],
            )
        )
        return out
