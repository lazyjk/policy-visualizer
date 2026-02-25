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
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  addEdge,
  useNodesState,
  useEdgesState,
  useNodesInitialized,
  useReactFlow,
  MarkerType,
  type Node,
  type Edge,
  type Connection,
  type NodeChange,
  type EdgeChange,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { toPng, toSvg } from "html-to-image";
import { jsPDF } from "jspdf";

import "@xyflow/react/dist/style.css";

import type { FlowIR } from "../api";
import { nodeTypes, DEFAULT_NODE_COLORS, type NodeColors } from "./nodes/nodeTypes";

// Fallback sizes used only when node.measured is undefined (shouldn't happen in pass 2).
const NODE_SIZE_FALLBACKS: Record<string, { width: number; height: number }> = {
  start: { width: 140, height: 60 },
  decision: { width: 220, height: 220 },
  process: { width: 180, height: 80 },
  action: { width: 160, height: 70 },
  end: { width: 130, height: 60 },
};

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  // Annotation nodes are freely positioned by the user — exclude them from dagre layout
  // and return them unchanged at the end.
  const diagNodes = nodes.filter((n) => n.type !== "annotation");
  const annNodes  = nodes.filter((n) => n.type === "annotation");

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 40 });

  diagNodes.forEach((node) => {
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
  const result = diagNodes.map((node) => {
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

  // Post-process: compress each rule chain vertically (all decisions at same x) and
  // reposition action nodes + their downstream nodes so there is no large horizontal gap.
  //
  // Key insight: dagre computes enf_chain x based on the longest path through the full
  // spread-out rm_chain, so it lands far to the right.  We instead place enf_chain
  // immediately after the rm_action nodes (enfChainStartX), then place end nodes right
  // next to their action node rather than leaving them at dagre positions.
  const nodeById = new Map(result.map((n) => [n.id, n]));

  const yesTarget = new Map<string, string>(); // source → YES-edge target id
  const noTarget  = new Map<string, string>(); // source → NO-edge target id
  const outEdges  = new Map<string, string[]>(); // source → all target ids
  edges.forEach((e) => {
    if (e.label === "YES") yesTarget.set(e.source, e.target);
    if (e.label === "NO")  noTarget.set(e.source, e.target);
    if (!outEdges.has(e.source)) outEdges.set(e.source, []);
    outEdges.get(e.source)!.push(e.target);
  });

  const fallbackDecision = NODE_SIZE_FALLBACKS.decision;
  const fallbackAction   = NODE_SIZE_FALLBACKS.action;
  const VERT_GAP     = 20;  // vertical gap between stacked chain nodes
  const LABEL_GAP    = 60;  // vertical gap when an end node is placed directly below its source
                            // (larger than VERT_GAP so the edge label has room between the nodes)
  const HORIZ_GAP    = 200;  // TODO(interactive): expose as a user-adjustable prop (slider/input in toolbar)
  const ACTION_INSET = 40;  // horizontal gap between decision right-edge and action left-edge

  // Move a non-chain node to sit immediately to the right of an action node.
  // If the target is itself an action node, recursively reposition its downstream.
  function placeAdjacentRight(actionNode: Node, targetId: string, actionRightX: number) {
    const target = nodeById.get(targetId);
    if (!target) return;
    const rg = target.data.rank_group as string | undefined;
    if (rg === "rm_chain" || rg === "enf_chain") return; // handled separately
    const dfb = NODE_SIZE_FALLBACKS[target.type ?? "end"] ?? { width: 130, height: 60 };
    const ah  = actionNode.measured?.height ?? fallbackAction.height;
    const dh  = target.measured?.height ?? dfb.height;
    target.position = {
      x: actionRightX + HORIZ_GAP,
      y: actionNode.position.y + (ah - dh) / 2,
    };
    if (target.type === "action") {
      const tw = target.measured?.width ?? fallbackAction.width;
      (outEdges.get(targetId) ?? []).forEach((tid) =>
        placeAdjacentRight(target, tid, actionRightX + HORIZ_GAP + tw)
      );
    }
  }

  // ---- rm_chain: stack decisions vertically, track rightmost edge for enf_chain ----
  let enfChainStartX: number | null = null;

  const rmGroup = result.filter(
    (n) => (n.data.rank_group as string | undefined) === "rm_chain"
  );
  if (rmGroup.length >= 1) {
    rmGroup.sort((a, b) => a.position.x - b.position.x);
    const chainX = rmGroup[0].position.x;
    let y = rmGroup[0].position.y;
    let maxRightX = chainX;

    for (let i = 0; i < rmGroup.length; i++) {
      const chainNode = rmGroup[i];
      const h = chainNode.measured?.height ?? fallbackDecision.height;
      const w = chainNode.measured?.width  ?? fallbackDecision.width;
      chainNode.position = { x: chainX, y };

      // YES branch: role action node → its downstream (enf_chain entry is skipped)
      const actionId = yesTarget.get(chainNode.id);
      if (actionId) {
        const actionNode = nodeById.get(actionId);
        if (actionNode) {
          const aw = actionNode.measured?.width  ?? fallbackAction.width;
          const ah = actionNode.measured?.height ?? fallbackAction.height;
          actionNode.position = {
            x: chainX + w + ACTION_INSET,
            y: y + (h - ah) / 2,
          };
          const actionRight = chainX + w + ACTION_INSET + aw;
          maxRightX = Math.max(maxRightX, actionRight);
          (outEdges.get(actionId) ?? []).forEach((tid) =>
            placeAdjacentRight(actionNode, tid, actionRight)
          );
        }
      }

      // Terminal NO node of the last decision (rm_default or no_role_end)
      if (i === rmGroup.length - 1) {
        const termId = noTarget.get(chainNode.id);
        if (termId) {
          const term = nodeById.get(termId);
          if (term && !(term.data.rank_group as string | undefined)) {
            const tw = term.measured?.width
              ?? (NODE_SIZE_FALLBACKS[term.type ?? "action"]?.width ?? 160);
            term.position = { x: chainX + w + ACTION_INSET, y: y + h + VERT_GAP };
            const termRight = chainX + w + ACTION_INSET + tw;
            maxRightX = Math.max(maxRightX, termRight);
            if (term.type === "action") {
              (outEdges.get(termId) ?? []).forEach((tid) =>
                placeAdjacentRight(term, tid, termRight)
              );
            }
          }
        }
      }

      y += h + VERT_GAP;
    }

    enfChainStartX = maxRightX + HORIZ_GAP;
  }

  // ---- enf_chain: same vertical stacking, x derived from rm_chain right edge ----
  const enfGroup = result.filter(
    (n) => (n.data.rank_group as string | undefined) === "enf_chain"
  );
  if (enfGroup.length >= 1) {
    enfGroup.sort((a, b) => a.position.x - b.position.x);
    const chainX = enfChainStartX ?? enfGroup[0].position.x;
    let y = enfGroup[0].position.y;

    for (let i = 0; i < enfGroup.length; i++) {
      const chainNode = enfGroup[i];
      const h = chainNode.measured?.height ?? fallbackDecision.height;
      const w = chainNode.measured?.width  ?? fallbackDecision.width;
      chainNode.position = { x: chainX, y };

      // YES branch: enforcement action node + its end node
      const actionId = yesTarget.get(chainNode.id);
      if (actionId) {
        const actionNode = nodeById.get(actionId);
        if (actionNode) {
          const aw = actionNode.measured?.width  ?? fallbackAction.width;
          const ah = actionNode.measured?.height ?? fallbackAction.height;
          actionNode.position = {
            x: chainX + w + ACTION_INSET,
            y: y + (h - ah) / 2,
          };
          const actionRight = chainX + w + ACTION_INSET + aw;
          (outEdges.get(actionId) ?? []).forEach((tid) =>
            placeAdjacentRight(actionNode, tid, actionRight)
          );
        }
      }

      // Terminal NO node of the last decision (enf_default_action or implicit deny)
      if (i === enfGroup.length - 1) {
        const termId = noTarget.get(chainNode.id);
        if (termId) {
          const term = nodeById.get(termId);
          if (term && !(term.data.rank_group as string | undefined)) {
            const tw = term.measured?.width
              ?? (NODE_SIZE_FALLBACKS[term.type ?? "action"]?.width ?? 160);
            term.position = { x: chainX + w + ACTION_INSET, y: y + h + VERT_GAP };
            const termRight = chainX + w + ACTION_INSET + tw;
            if (term.type === "action") {
              (outEdges.get(termId) ?? []).forEach((tid) =>
                placeAdjacentRight(term, tid, termRight)
              );
            }
          }
        }
      }

      y += h + VERT_GAP;
    }
  }

  // ---- Overlap detection and resolution ----
  // After chain compression, non-chain nodes (e.g. auth_fail) keep their original
  // dagre positions which may now overlap compressed chain nodes. Detect, log, and
  // relocate them to sit below their source node instead.

  function nodeBBox(n: Node) {
    const fb = NODE_SIZE_FALLBACKS[n.type ?? "process"] ?? { width: 160, height: 80 };
    return { x: n.position.x, y: n.position.y, w: n.measured?.width ?? fb.width, h: n.measured?.height ?? fb.height };
  }

  function bboxOverlap(a: ReturnType<typeof nodeBBox>, b: ReturnType<typeof nodeBBox>): boolean {
    const P = 8; // padding so nodes touching closely also count
    return a.x - P < b.x + b.w && a.x + a.w + P > b.x && a.y - P < b.y + b.h && a.y + a.h + P > b.y;
  }

  const inEdges = new Map<string, string[]>(); // target id → source ids
  edges.forEach((e) => {
    if (!inEdges.has(e.target)) inEdges.set(e.target, []);
    inEdges.get(e.target)!.push(e.source);
  });

  const chainIds = new Set<string>([...rmGroup.map((n) => n.id), ...enfGroup.map((n) => n.id)]);

  // Step 1: Snap NO-branch targets of non-chain decision nodes directly below them.
  // This applies to nodes like svc_match whose NO exit (no_match_end / "Skip") should
  // go straight down rather than curving sideways to wherever dagre placed them.
  result.forEach((node) => {
    if (node.type !== "decision" || chainIds.has(node.id)) return;
    const noTargetId = noTarget.get(node.id);
    if (!noTargetId) return;
    const noTargetNode = nodeById.get(noTargetId);
    if (!noTargetNode || chainIds.has(noTargetNode.id)) return;
    const nb = nodeBBox(node);
    const ntfb = NODE_SIZE_FALLBACKS[noTargetNode.type ?? "end"] ?? { width: 130, height: 60 };
    const ntw = noTargetNode.measured?.width ?? ntfb.width;
    noTargetNode.position = {
      x: node.position.x + (nb.w - ntw) / 2,
      y: node.position.y + nb.h + LABEL_GAP,
    };
  });

  // Step 2: Relocate any non-chain node that overlaps a chain node OR that dagre
  // placed in the same x column as a chain node but whose source is to the left.
  // Place it below its source, then nudge downward past any other non-chain node
  // it would land on top of (e.g. auth_fail below auth_node must not collide with
  // no_match_end which was just snapped below svc_match in step 1).
  result.forEach((node) => {
    if (chainIds.has(node.id)) return;
    const nb = nodeBBox(node);
    const collidesChain = [...chainIds].some((cid) => {
      const cn = nodeById.get(cid);
      return cn ? bboxOverlap(nb, nodeBBox(cn)) : false;
    });

    const sources = inEdges.get(node.id) ?? [];

    // Also catch nodes that dagre placed in the same x column as a chain node but
    // whose source is to the left of the chain (e.g. auth_fail shares a dagre rank
    // with rm_rule_0 but its source, auth_node, is one rank to the left). Without
    // this check, auth_fail sits at rm_rule_0.x and blocks the NO edge routing path.
    const inChainXColumn = !collidesChain && [...chainIds].some((cid) => {
      const cn = nodeById.get(cid);
      if (!cn) return false;
      const cb = nodeBBox(cn);
      const xOverlaps = nb.x - 8 < cb.x + cb.w && nb.x + nb.w + 8 > cb.x;
      if (!xOverlaps) return false;
      return sources.every((srcId) => {
        const src = nodeById.get(srcId);
        return src ? src.position.x + (src.measured?.width ?? 160) <= cb.x : false;
      });
    });

    if (!collidesChain && !inChainXColumn) return;
    if (sources.length === 0) return;
    const srcNode = nodeById.get(sources[0]);
    if (!srcNode) return;
    const sb = nodeBBox(srcNode);
    const nfb = NODE_SIZE_FALLBACKS[node.type ?? "end"] ?? { width: 130, height: 60 };
    const nw = node.measured?.width ?? nfb.width;
    const nh = node.measured?.height ?? nfb.height;

    let newX = srcNode.position.x + (sb.w - nw) / 2;
    // Use the larger LABEL_GAP for end nodes so the edge label is visible above them.
    let newY = srcNode.position.y + sb.h + (node.type === "end" ? LABEL_GAP : VERT_GAP);

    // Nudge downward if the candidate position would land on another non-chain node.
    for (let attempt = 0; attempt < 8; attempt++) {
      const candidate = { x: newX, y: newY, w: nw, h: nh };
      const conflict = result.find(
        (other) => other.id !== node.id && !chainIds.has(other.id) && bboxOverlap(candidate, nodeBBox(other))
      );
      if (!conflict) break;
      const cb = nodeBBox(conflict);
      newY = cb.y + cb.h + VERT_GAP;
    }

    node.position = { x: newX, y: newY };
  });

  // Log any overlaps that remain after all repositioning (dev aid).
  const overlapPairs: [string, string][] = [];
  for (let i = 0; i < result.length; i++) {
    for (let j = i + 1; j < result.length; j++) {
      if (bboxOverlap(nodeBBox(result[i]), nodeBBox(result[j]))) {
        overlapPairs.push([result[i].id, result[j].id]);
      }
    }
  }
  if (overlapPairs.length > 0) {
    console.warn("[FlowDiagram] Overlapping nodes after layout:", overlapPairs);
  }

  // Return diagram nodes (now positioned) + annotation nodes (positions unchanged).
  return [...result, ...annNodes];
}

// ---------------------------------------------------------------------------
// ExportPanel — rendered inside <ReactFlow> so it can call useReactFlow()
// ---------------------------------------------------------------------------

interface ExportPanelProps {
  wrapperRef: React.RefObject<HTMLDivElement | null>;
  serviceName: string;
}

function ExportPanel({ wrapperRef, serviceName }: ExportPanelProps) {
  const { fitView, getViewport, setViewport } = useReactFlow();
  const [exporting, setExporting] = useState(false);
  const [transparentBg, setTransparentBg] = useState(false);

  const captureImage = useCallback(
    async (format: "png" | "svg", transparent: boolean): Promise<string> => {
      const saved = getViewport();
      fitView({ duration: 0, padding: 0.1 });
      // Wait two animation frames so React Flow commits the viewport change.
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
      );
      const options = {
        filter: (el: HTMLElement) => {
          const cl = el.classList;
          if (!cl) return true;
          // Exclude React Flow UI chrome (controls, minimap, panels) from the export.
          return (
            !cl.contains("react-flow__panel") &&
            !cl.contains("react-flow__controls") &&
            !cl.contains("react-flow__minimap")
          );
        },
        ...(transparent ? {} : { backgroundColor: "#ffffff" }),
      };
      const dataUrl =
        format === "svg"
          ? await toSvg(wrapperRef.current!, options)
          : await toPng(wrapperRef.current!, options);
      setViewport(saved, { duration: 0 });
      return dataUrl;
    },
    [fitView, getViewport, setViewport, wrapperRef]
  );

  const handleExportPng = useCallback(async () => {
    if (exporting || !wrapperRef.current) return;
    setExporting(true);
    try {
      const dataUrl = await captureImage("png", transparentBg);
      const a = document.createElement("a");
      a.href = dataUrl;
      a.download = `${serviceName}.png`;
      a.click();
    } finally {
      setExporting(false);
    }
  }, [exporting, captureImage, serviceName, transparentBg, wrapperRef]);

  const handleExportSvg = useCallback(async () => {
    if (exporting || !wrapperRef.current) return;
    setExporting(true);
    try {
      const dataUrl = await captureImage("svg", transparentBg);
      const a = document.createElement("a");
      a.href = dataUrl;
      a.download = `${serviceName}.svg`;
      a.click();
    } finally {
      setExporting(false);
    }
  }, [exporting, captureImage, serviceName, transparentBg, wrapperRef]);

  const handleExportPdf = useCallback(async () => {
    if (exporting || !wrapperRef.current) return;
    setExporting(true);
    try {
      const dataUrl = await captureImage("png", transparentBg);
      const img = new Image();
      img.src = dataUrl;
      await new Promise<void>((resolve) => { img.onload = () => resolve(); });
      const pdf = new jsPDF({
        orientation: img.width > img.height ? "landscape" : "portrait",
        unit: "px",
        format: [img.width, img.height],
      });
      pdf.addImage(dataUrl, "PNG", 0, 0, img.width, img.height);
      pdf.save(`${serviceName}.pdf`);
    } finally {
      setExporting(false);
    }
  }, [exporting, captureImage, serviceName, transparentBg, wrapperRef]);

  const btnLabel = exporting ? "Exporting…" : null;

  return (
    <Panel position="top-right">
      <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={handleExportPng} disabled={exporting}>
            {btnLabel ?? "Export PNG"}
          </button>
          <button onClick={handleExportSvg} disabled={exporting}>
            {btnLabel ?? "Export SVG"}
          </button>
          <button onClick={handleExportPdf} disabled={exporting}>
            {btnLabel ?? "Export PDF"}
          </button>
        </div>
        <label style={{ fontSize: 11, color: "#555", cursor: "pointer", userSelect: "none" }}>
          <input
            type="checkbox"
            checked={transparentBg}
            onChange={(e) => setTransparentBg(e.target.checked)}
            style={{ marginRight: 4 }}
          />
          Transparent background
        </label>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// AnnotationPanel — "Add Note" + "Snap" toggle; rendered inside <ReactFlow>
// ---------------------------------------------------------------------------

interface AnnotationPanelProps {
  snapToGrid: boolean;
  setSnapToGrid: React.Dispatch<React.SetStateAction<boolean>>;
  nodeColors: NodeColors;
}

function AnnotationPanel({ snapToGrid, setSnapToGrid, nodeColors }: AnnotationPanelProps) {
  const { screenToFlowPosition, setNodes } = useReactFlow();

  const addAnnotation = useCallback(() => {
    const pos = screenToFlowPosition({
      x: window.innerWidth / 2,
      y: window.innerHeight / 2,
    });
    setNodes((nds) => [
      ...nds,
      {
        id: `annotation-${Date.now()}`,
        type: "annotation",
        position: pos,
        data: { text: "", colors: nodeColors },
      },
    ]);
  }, [screenToFlowPosition, setNodes, nodeColors]);

  return (
    <Panel position="top-left">
      <div style={{ display: "flex", gap: 6 }}>
        <button onClick={addAnnotation}>Add Note</button>
        <button
          onClick={() => setSnapToGrid((s) => !s)}
          style={snapToGrid ? { background: "#AED6F1", fontWeight: 600 } : undefined}
        >
          {snapToGrid ? "Snap: On" : "Snap: Off"}
        </button>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// StylePanel — per-shape color picker; rendered inside <ReactFlow>
// ---------------------------------------------------------------------------

interface StylePanelProps {
  nodeColors: NodeColors;
  setNodeColors: React.Dispatch<React.SetStateAction<NodeColors>>;
}

const NODE_COLOR_LABELS: { key: keyof NodeColors; label: string }[] = [
  { key: "start",      label: "Start" },
  { key: "decision",   label: "Decision" },
  { key: "process",    label: "Process" },
  { key: "action",     label: "Action" },
  { key: "end",        label: "End" },
  { key: "annotation", label: "Annotation" },
];

function StylePanel({ nodeColors, setNodeColors }: StylePanelProps) {
  return (
    <Panel position="bottom-left" style={{ marginLeft: 62 }}>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 5,
          background: "white",
          border: "1px solid #e5e7eb",
          borderRadius: 6,
          padding: "8px 10px",
          boxShadow: "0 1px 4px rgba(0,0,0,0.1)",
        }}
      >
        <div style={{ fontSize: 11, fontWeight: 600, color: "#333", marginBottom: 1 }}>
          Node Colors
        </div>
        {NODE_COLOR_LABELS.map(({ key, label }) => (
          <label
            key={key}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              cursor: "pointer",
              fontSize: 11,
              color: "#555",
              userSelect: "none",
            }}
          >
            <span
              style={{
                width: 16,
                height: 16,
                backgroundColor: nodeColors[key],
                border: "1px solid #aaa",
                borderRadius: 3,
                display: "inline-block",
                flexShrink: 0,
              }}
            />
            <input
              type="color"
              value={nodeColors[key]}
              onChange={(e) =>
                setNodeColors((prev) => ({ ...prev, [key]: e.target.value }))
              }
              style={{
                width: 0,
                height: 0,
                opacity: 0,
                padding: 0,
                border: "none",
                position: "absolute",
              }}
            />
            {label}
          </label>
        ))}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------

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
  const flowWrapperRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [layoutApplied, setLayoutApplied] = useState(false);
  const [nodeColors, setNodeColors] = useState<NodeColors>(DEFAULT_NODE_COLORS);
  const [snapToGrid, setSnapToGrid] = useState(false);
  // Ref so the flow-load effect always uses the current colors without re-running layout.
  const nodeColorsRef = useRef(nodeColors);
  nodeColorsRef.current = nodeColors;

  // Only annotation nodes can be deleted; diagram nodes are immutable.
  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      onNodesChange(
        changes.filter(
          (c) => c.type !== "remove" || nodes.find((n) => n.id === c.id)?.type === "annotation"
        )
      );
    },
    [onNodesChange, nodes]
  );

  // Only annotation edges (data.isAnnotation) can be deleted.
  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      onEdgesChange(
        changes.filter(
          (c) => c.type !== "remove" || edges.find((e) => e.id === c.id)?.data?.isAnnotation
        )
      );
    },
    [onEdgesChange, edges]
  );

  // Connections may only originate from annotation nodes.
  const onConnect = useCallback(
    (connection: Connection) => {
      const src = nodes.find((n) => n.id === connection.source);
      if (src?.type !== "annotation") return;
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: `ann-edge-${Date.now()}`,
            type: "smoothstep",
            style: { stroke: "#9B59B6", strokeWidth: 1.5, strokeDasharray: "5,5" },
            markerEnd: { type: MarkerType.ArrowClosed, color: "#9B59B6", width: 12, height: 12 },
            data: { isAnnotation: true },
          },
          eds
        )
      );
    },
    [nodes, setEdges]
  );

  // Propagate color changes to all existing nodes (including user-placed annotations).
  useEffect(() => {
    setNodes((nds) => nds.map((n) => ({ ...n, data: { ...n.data, colors: nodeColors } })));
  }, [nodeColors, setNodes]);

  useEffect(() => {
    const rawNodes: Node[] = flow.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      data: {
        label: n.label,
        sub_label: n.sub_label,
        trace_rule_id: n.trace_rule_id,
        rank_group: n.rank_group,
        colors: nodeColorsRef.current,
      },
      position: { x: 0, y: 0 },
    }));

    const nodeTypeById = new Map(flow.nodes.map((n) => [n.id, n.type]));
    const rawEdges: Edge[] = flow.edges.map((e, i) => ({
      id: `edge-${i}`,
      type: "smoothstep",
      source: e.from_id,
      target: e.to_id,
      sourceHandle: e.label === "YES" ? "yes" : e.label === "NO" ? "no" : e.label === "FAIL" ? "fail" : undefined,
      targetHandle: (() => {
        const tt = nodeTypeById.get(e.to_id);
        // NO chain edges arrive from above — use top handle.
        if (e.label === "NO" && tt === "decision") return "top";
        // NO/FAIL terminal edges arrive from above — use top handle.
        if ((e.label === "NO" || e.label === "FAIL") && tt === "end") return "top";
        // All other forward-path edges to decisions use the explicit left handle.
        if (tt === "decision") return "left";
        // All other forward-path edges to end nodes use the explicit left handle.
        if (tt === "end") return "left";
        return undefined;
      })(),
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
    <div ref={flowWrapperRef} style={{ width: "100%", height: "100%" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView={false}
        minZoom={0.1}
        maxZoom={3}
        snapToGrid={snapToGrid}
        snapGrid={[20, 20]}
      >
        <Background gap={16} color="#e5e7eb" />
        <Controls />
        <MiniMap
          nodeColor={(node) => nodeColors[node.type as keyof NodeColors] ?? "#ccc"}
          style={{ background: "#f9fafb", border: "1px solid #e5e7eb" }}
        />
        <AnnotationPanel
          snapToGrid={snapToGrid}
          setSnapToGrid={setSnapToGrid}
          nodeColors={nodeColors}
        />
        <StylePanel nodeColors={nodeColors} setNodeColors={setNodeColors} />
        <LayoutEffect
          layoutApplied={layoutApplied}
          setLayoutApplied={setLayoutApplied}
        />
        <ExportPanel wrapperRef={flowWrapperRef} serviceName={flow.service_name} />
      </ReactFlow>
    </div>
  );
}
