from outreachos_backend.rendering.geometry import OUTPUT_FPS
from outreachos_backend.rendering.graph import FilterNode, GraphContext, GraphStep


class FpsStep(GraphStep):
    step_id = "fps"

    def apply(self, ctx: GraphContext, current: str) -> str:
        out = ctx.new_label("fps")
        ctx.add_node(
            FilterNode(
                id=self.step_id,
                filter=f"fps={OUTPUT_FPS}",
                inputs=[current],
                outputs=[out],
            )
        )
        return out
