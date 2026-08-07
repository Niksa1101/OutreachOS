from outreachos_backend.rendering.graph import FilterNode, GraphContext, GraphStep


class PaddingPadStep(GraphStep):
    """Seat the inner (padded) crop inside the full box, leaving a transparent ring.

    The ring stays transparent here — `alphamerge` downstream sets alpha from the
    mask, which is already inset by the same padding, so the background layer
    shows through where this step leaves the video content absent.
    """

    step_id = "padding_pad"

    def __init__(self, box_width: int, box_height: int, padding: int) -> None:
        self.box_width = box_width
        self.box_height = box_height
        self.padding = padding

    def apply(self, ctx: GraphContext, current: str) -> str:
        if self.padding <= 0:
            return current
        out = ctx.new_label("padpad")
        ctx.add_node(
            FilterNode(
                id=self.step_id,
                filter=(
                    f"pad={self.box_width}:{self.box_height}"
                    f":{self.padding}:{self.padding}:color=0x00000000"
                ),
                inputs=[current],
                outputs=[out],
            )
        )
        return out
