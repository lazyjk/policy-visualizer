/**
 * FlowDiagram — two-pass layout using React Flow's DOM measurement system.
 *
 * Pass 1: Set nodes at (0,0). React Flow measures actual rendered sizes via ResizeObserver.
 * Pass 2: Once all nodes measured (useNodesInitialized), run dagre with those
 *         real dimensions and update positions. Then fitView.
 *
 * LayoutEffect is rendered *inside* <ReactFlow> so it has access to context hooks
 * (useNodesInitialized, useReactFlow) which are not available in the parent.
 */
import { useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useNodesInitialized,
  useReactFlow,
  MarkerType,
  type Node,
  type Edge,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";

import "@xyflow/react/dist/style.css";

import type { FlowIR } from "../api";
import { nodeTypes } from "./nodes/nodeTypes";

// Fallback sizes used only when node.measured is undefined (shouldn't happen in pass 2).
const NODE_SIZE_FALLBACKS: Record<string, { width: number; height: number }> = {
  start: { width: 140, height: 60 },
  decision: { width: 220, height: 220 },
  process: { width: 180, height: 80 },
  action: { width: 160, height: 70 },
  end: { width: 130, height: 60 },
};

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 80 });

  nodes.forEach((node) => {
    const fallback = NODE_SIZE_FALLBACKS[node.type ?? "process"] ?? { width: 160, height: 80 };
    const width = node.measured?.width ?? fallback.width;
    const height = node.measured?.height ?? fallback.height;
    g.setNode(node.id, { width, height });
  });

  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  // Build positioned result — each node is a fresh object so we can mutate position below.
  const result = nodes.map((node) => {
    const pos = g.node(node.id);
    const fallback = NODE_SIZE_FALLBACKS[node.type ?? "process"] ?? { width: 160, height: 80 };
    const width = node.measured?.width ?? fallback.width;
    const height = node.measured?.height ?? fallback.height;
    return {
      ...node,
      position: {
        x: pos.x - width / 2,
        y: pos.y - height / 2,
      },
    };
  });

  // Post-process: snap nodes in the same rank_group to the same x-column and stack
  // them vertically. This replicates graphviz {rank=same} without touching dagre's
  // algorithm (which can crash on minlen:0 in some graph shapes).
  const nodeById = new Map(result.map((n) => [n.id, n]));
  const yesTarget = new Map<string, string>(); // decisionId → YES-edge target id
  edges.forEach((e) => {
    if (e.label === "YES") yesTarget.set(e.source, e.target);
  });

  for (const groupName of ["rm_chain", "enf_chain"]) {
    const group = result.filter(
      (n) => (n.data.rank_group as string | undefined) === groupName
    );
    if (group.length < 2) continue;

    // In dagre LR the NO-chain spreads decisions horizontally; sort by x gives chain order.
    group.sort((a, b) => a.position.x - b.position.x);

    const chainX = group[0].position.x;
    const fallbackDecision = NODE_SIZE_FALLBACKS.decision;
    const fallbackAction = NODE_SIZE_FALLBACKS.action;
    const gap = 20; // vertical gap between successive chain nodes
    let y = group[0].position.y;

    for (const chainNode of group) {
      const h = chainNode.measured?.height ?? fallbackDecision.height;
      const w = chainNode.measured?.width ?? fallbackDecision.width;
      chainNode.position = { x: chainX, y };

      // Align the YES-edge action node to be vertically centred beside this decision.
      const actionId = yesTarget.get(chainNode.id);
      if (actionId) {
        const actionNode = nodeById.get(actionId);
        if (actionNode) {
          const ah = actionNode.measured?.height ?? fallbackAction.height;
          actionNode.position = {
            x: chainX + w + 40,
            y: y + (h - ah) / 2,
          };
        }
      }

      y += h + gap;
    }
  }

  return result;
}

interface LayoutEffectProps {
  layoutApplied: boolean;
  setLayoutApplied: (val: boolean) => void;
}

/** Rendered inside <ReactFlow> so it can use React Flow context hooks. */
function LayoutEffect({ layoutApplied, setLayoutApplied }: LayoutEffectProps) {
  const nodesInitialized = useNodesInitialized();
  const { setNodes, fitView, getEdges } = useReactFlow();

  useEffect(() => {
    if (!nodesInitialized || layoutApplied) return;
    const edges = getEdges();
    setNodes((nds) => applyDagreLayout(nds, edges));
    setLayoutApplied(true);
    // Brief delay to let React Flow commit the position update before fitting the view.
    setTimeout(() => fitView({ padding: 0.15 }), 50);
  }, [nodesInitialized, layoutApplied, getEdges, setNodes, fitView, setLayoutApplied]);

  return null;
}

interface Props {
  flow: FlowIR;
}

export default function FlowDiagram({ flow }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [layoutApplied, setLayoutApplied] = useState(false);

  useEffect(() => {
    const rawNodes: Node[] = flow.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      data: {
        label: n.label,
        sub_label: n.sub_label,
        trace_rule_id: n.trace_rule_id,
        rank_group: n.rank_group,
      },
      position: { x: 0, y: 0 },
    }));

    const rawEdges: Edge[] = flow.edges.map((e, i) => ({
      id: `edge-${i}`,
      source: e.from_id,
      target: e.to_id,
      label: e.label || undefined,
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12 },
      style: { stroke: "#555", strokeWidth: 1.5 },
      labelStyle: { fontSize: 10, fontFamily: "Helvetica, Arial, sans-serif" },
      labelBgStyle: { fill: "#fff", fillOpacity: 0.8 },
    }));

    setNodes(rawNodes);
    setEdges(rawEdges);
    setLayoutApplied(false); // Reset so layout runs again when a new flow loads.
  }, [flow, setNodes, setEdges]);

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView={false}
        minZoom={0.1}
        maxZoom={3}
      >
        <Background gap={16} color="#e5e7eb" />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            const colors: Record<string, string> = {
              start: "#AED6F1",
              decision: "#FAD7A0",
              process: "#A9DFBF",
              action: "#D7BDE2",
              end: "#F1948A",
            };
            return colors[node.type ?? "process"] ?? "#ccc";
          }}
          style={{ background: "#f9fafb", border: "1px solid #e5e7eb" }}
        />
        <LayoutEffect
          layoutApplied={layoutApplied}
          setLayoutApplied={setLayoutApplied}
        />
      </ReactFlow>
    </div>
  );
}
