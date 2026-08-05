from outreachos_backend.rendering.geometry import CANVAS_HEIGHT, CANVAS_WIDTH
from outreachos_backend.rendering.graph import FilterNode, GraphContext, GraphStep


class ScalePadStep(GraphStep):
    step_id = "scale_pad"

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def apply(self, ctx: GraphContext, current: str) -> str:
        out = ctx.new_label("scale")
        ctx.add_node(
            FilterNode(
                id=self.step_id,
                filter=f"scale={CANVAS_WIDTH}:{CANVAS_HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={CANVAS_WIDTH}:{CANVAS_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
                inputs=[current],
                outputs=[out],
            )
        )
        return out
