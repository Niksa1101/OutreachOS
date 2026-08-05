from outreachos_backend.rendering.graph import FilterNode, GraphContext, GraphStep


class TpadStep(GraphStep):
    step_id = "tpad"

    def __init__(self, pad_duration_s: float) -> None:
        self.pad_duration_s = max(0.0, pad_duration_s)

    def apply(self, ctx: GraphContext, current: str) -> str:
        if self.pad_duration_s <= 0:
            return current
        out = ctx.new_label("tpad")
        ctx.add_node(
            FilterNode(
                id=self.step_id,
                filter=f"tpad=stop_mode=clone:stop_duration={self.pad_duration_s:.6f}",
                inputs=[current],
                outputs=[out],
            )
        )
        return out
