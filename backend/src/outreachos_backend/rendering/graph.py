"""Filtergraph builder with explicit input registration."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["FilterNode", "GraphContext", "GraphInput", "GraphStep", "render_graph"]


@dataclass(frozen=True)
class GraphInput:
    """One FFmpeg input: the source plus the options that must precede its ``-i``."""

    path: str
    options: tuple[str, ...] = ()


@dataclass
class FilterNode:
    id: str
    filter: str
    inputs: list[str]
    outputs: list[str]
    label: str | None = None


@dataclass
class GraphContext:
    inputs: list[GraphInput] = field(default_factory=list)
    nodes: list[FilterNode] = field(default_factory=list)
    _label_counter: int = 0

    def add_input(self, path: str, *options: str) -> str:
        """Register an input and return the stream index the filtergraph refers to.

        Per-input options are captured here rather than assembled separately by the
        caller: the filtergraph addresses inputs by position, so an ``-i`` list built
        anywhere else is a second source of truth that can silently drift out of order.
        """
        index = len(self.inputs)
        self.inputs.append(GraphInput(path=path, options=tuple(options)))
        return str(index)

    def input_args(self) -> list[str]:
        """The ``-i`` arguments for this graph, in registration order."""
        args: list[str] = []
        for item in self.inputs:
            args.extend(item.options)
            args.extend(["-i", item.path])
        return args

    def new_label(self, prefix: str = "v") -> str:
        self._label_counter += 1
        return f"{prefix}{self._label_counter}"

    def add_node(self, node: FilterNode) -> None:
        self.nodes.append(node)


class GraphStep:
    step_id: str

    def apply(self, ctx: GraphContext, current: str) -> str:
        raise NotImplementedError


def render_graph(ctx: GraphContext, final_label: str) -> tuple[str, str]:
    """Return ffmpeg -filter_complex string and mapped output label."""
    parts: list[str] = []
    for node in ctx.nodes:
        ins = "".join(f"[{i}]" for i in node.inputs)
        outs = "".join(f"[{o}]" for o in node.outputs)
        parts.append(f"{ins}{node.filter}{outs}")
    return ";".join(parts), final_label
