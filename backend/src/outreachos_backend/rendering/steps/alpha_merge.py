from outreachos_backend.rendering.graph import FilterNode, GraphContext, GraphStep


class AlphaMergeStep(GraphStep):
    step_id = "alphamerge"

    def __init__(self, mask_input: str) -> None:
        self.mask_input = mask_input

    def apply(self, ctx: GraphContext, current: str) -> str:
        out = ctx.new_label("am")
        ctx.add_node(
            FilterNode(
                id=self.step_id,
                filter="alphamerge",
                inputs=[current, self.mask_input],
                outputs=[out],
            )
        )
        return out


class AlphaCompositeStep(GraphStep):
    step_id = "composite"

    def __init__(self, backdrop_input: str, frame_input: str) -> None:
        self.backdrop_input = backdrop_input
        self.frame_input = frame_input

    def apply(self, ctx: GraphContext, current: str) -> str:
        over_back = ctx.new_label("comp1")
        ctx.add_node(
            FilterNode(
                id=f"{self.step_id}_backdrop",
                filter="overlay=0:0",
                inputs=[self.backdrop_input, current],
                outputs=[over_back],
            )
        )
        out = ctx.new_label("comp2")
        ctx.add_node(
            FilterNode(
                id=f"{self.step_id}_frame",
                filter="overlay=0:0",
                inputs=[over_back, self.frame_input],
                outputs=[out],
            )
        )
        return out
