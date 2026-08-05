from outreachos_backend.rendering.graph import FilterNode, GraphContext, GraphStep


class BleedPadStep(GraphStep):
    """Seat the cropped box inside the bleed box (ADR-0008).

    The transparent pad colour only survives because `alphamerge` downstream sets
    alpha from the mask; the pad itself just reserves the shadow's margin.
    """

    step_id = "bleed_pad"

    def __init__(
        self, bleed_width: int, bleed_height: int, inset_left: int, inset_top: int
    ) -> None:
        self.bleed_width = bleed_width
        self.bleed_height = bleed_height
        self.inset_left = inset_left
        self.inset_top = inset_top

    def apply(self, ctx: GraphContext, current: str) -> str:
        out = ctx.new_label("pad")
        ctx.add_node(
            FilterNode(
                id=self.step_id,
                filter=(
                    f"pad={self.bleed_width}:{self.bleed_height}"
                    f":{self.inset_left}:{self.inset_top}:color=0x00000000"
                ),
                inputs=[current],
                outputs=[out],
            )
        )
        return out
