from outreachos_backend.rendering.graph import FilterNode, GraphContext, GraphStep


class OverlayStep(GraphStep):
    step_id = "overlay"

    def __init__(self, alpha_input: str, x: int, y: int) -> None:
        self.alpha_input = alpha_input
        self.x = x
        self.y = y

    def apply(self, ctx: GraphContext, current: str) -> str:
        out = ctx.new_label("ov")
        ctx.add_node(
            FilterNode(
                id=self.step_id,
                filter=f"overlay={self.x}:{self.y}",
                inputs=[current, self.alpha_input],
                outputs=[out],
            )
        )
        return out
