from outreachos_backend.rendering.graph import FilterNode, GraphContext, GraphStep


class FocalCropStep(GraphStep):
    """Fill the overlay box from the talking head, cropped around the focal point.

    `force_original_aspect_ratio=increase` scales to cover, so the crop that follows
    always has pixels to take; `iw`/`ih` inside it refer to the scaled frame.
    """

    step_id = "focal_crop"

    def __init__(self, box_width: int, box_height: int, focal_x: float, focal_y: float) -> None:
        self.box_width = box_width
        self.box_height = box_height
        self.focal_x = focal_x
        self.focal_y = focal_y

    def apply(self, ctx: GraphContext, current: str) -> str:
        out = ctx.new_label("crop")
        ctx.add_node(
            FilterNode(
                id=self.step_id,
                filter=(
                    f"scale={self.box_width}:{self.box_height}"
                    f":force_original_aspect_ratio=increase,"
                    f"crop={self.box_width}:{self.box_height}:"
                    f"(iw-{self.box_width})*{self.focal_x}:"
                    f"(ih-{self.box_height})*{self.focal_y}"
                ),
                inputs=[current],
                outputs=[out],
            )
        )
        return out
