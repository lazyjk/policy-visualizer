"""
Phase 5: Rendering Layer

Converts a FlowIR into an SVG diagram via Graphviz (dot engine).
Layout: left-to-right (rankdir=LR).
Node shapes follow the spec: start=ellipse, decision=diamond,
process=rectangle, action=rounded-rectangle, end=doublecircle.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import graphviz

from .flow_ir import FlowIR, FlowNode

# Node visual style per type
_STYLES: dict[str, dict[str, str]] = {
    "start": {
        "shape": "ellipse",
        "style": "filled",
        "fillcolor": "#AED6F1",
        "fontsize": "10",
    },
    "decision": {
        "shape": "diamond",
        "style": "filled",
        "fillcolor": "#FAD7A0",
        "fontsize": "9",
    },
    "process": {
        "shape": "rectangle",
        "style": "filled",
        "fillcolor": "#A9DFBF",
        "fontsize": "10",
    },
    "action": {
        "shape": "box",
        "style": "rounded,filled",
        "fillcolor": "#D7BDE2",
        "fontsize": "10",
    },
    "end": {
        "shape": "doublecircle",
        "style": "filled",
        "fillcolor": "#F1948A",
        "fontsize": "10",
    },
}


def _node_attrs(node: FlowNode) -> dict[str, str]:
    base = dict(_STYLES.get(node.type, {}))
    label = node.label
    if node.sub_label:
        label += f"\n{node.sub_label}"
    base["label"] = label
    return base


def render(flow: FlowIR, output_path: str | Path, fmt: str = "svg") -> Path:
    """
    Render the FlowIR to a file.

    Parameters
    ----------
    flow        : FlowIR to render
    output_path : destination file path (without extension)
    fmt         : output format, default "svg"

    Returns
    -------
    Path to the rendered file.
    """
    output_path = Path(output_path)
    # Strip extension if provided — graphviz appends it
    stem = output_path.with_suffix("") if output_path.suffix else output_path

    dot = graphviz.Digraph(
        name=flow.service_name,
        comment=f"ClearPass flow: {flow.service_name}",
    )
    dot.attr(
        rankdir="LR",
        splines="polyline",
        nodesep="0.4",
        ranksep="0.7",
        fontname="Helvetica",
        fontsize="11",
        overlap="false",
    )
    dot.attr("node", fontname="Helvetica")
    dot.attr("edge", fontname="Helvetica", fontsize="8", arrowsize="0.7")

    # Add all nodes
    for node in flow.nodes:
        attrs = _node_attrs(node)
        dot.node(node.id, **attrs)

    # Stack rule chains vertically via rank=same subgraphs
    rank_groups: dict[str, list[str]] = defaultdict(list)
    for node in flow.nodes:
        if node.rank_group:
            rank_groups[node.rank_group].append(node.id)
    for node_ids in rank_groups.values():
        with dot.subgraph() as sg:
            sg.attr(rank="same")
            for nid in node_ids:
                sg.node(nid)

    # Add all edges
    for edge in flow.edges:
        label = edge.label or ""
        dot.edge(edge.from_id, edge.to_id, label=label)

    # Render
    rendered = dot.render(
        filename=str(stem),
        format=fmt,
        cleanup=True,   # remove the intermediate .dot source file
    )
    return Path(rendered)


def render_dot_source(flow: FlowIR) -> str:
    """Return the raw Graphviz dot source string (for testing / inspection)."""
    dot = graphviz.Digraph(name=flow.service_name)
    dot.attr(rankdir="LR", splines="ortho")
    dot.attr("node", fontname="Helvetica")
    for node in flow.nodes:
        attrs = _node_attrs(node)
        dot.node(node.id, **attrs)
    for edge in flow.edges:
        dot.edge(edge.from_id, edge.to_id, label=edge.label or "")
    return dot.source
