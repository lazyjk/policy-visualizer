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

import { fetchFlow } from "../api";
import type { FlowIR, ServiceSummary } from "../api";
import { nodeTypes, DEFAULT_NODE_COLORS, type NodeColors } from "./nodes/nodeTypes";
import {
  useDiagramSession,
  type DiagramEditState,
  type AnnotationClipboard,
} from "../context/DiagramSessionContext";

// Fallback sizes used only when node.measured is undefined (shouldn't happen in pass 2).
const NODE_SIZE_FALLBACKS: Record<string, { width: number; height: number }> = {
  start: { width: 140, height: 60 },
  decision: { width: 220, height: 220 },
  process: { width: 180, height: 80 },
  action: { width: 160, height: 70 },
  end: { width: 130, height: 60 },
};

type DiagramNodeType = FlowIR["nodes"][number]["type"] | "annotation";
type BranchClass = "forward" | "no" | "fail" | "unknown";

// Connector policy (preference-locked):
// - Global direction: left → right
// - Decision exits: YES/PASS forward-right, NO downward
// - Process exits: forward-right default, FAIL downward
// - End entry: forward enters left, NO/FAIL enters top
function normalizeEdgeLabel(label?: string): string | undefined {
  const normalized = label?.trim().toUpperCase();
  return normalized ? normalized : undefined;
}

function getBranchClass(label?: string): BranchClass {
  const normalized = normalizeEdgeLabel(label);
  if (normalized === "YES" || normalized === "PASS" || normalized === "CONTINUE") return "forward";
  if (normalized === "NO") return "no";
  if (normalized === "FAIL") return "fail";
  return "unknown";
}

function resolveSourceHandle(sourceType: DiagramNodeType | undefined, label?: string): string | undefined {
  const branch = getBranchClass(label);
  switch (sourceType) {
    case "decision":
      return branch === "no" ? "no" : "yes";
    case "process":
      if (branch === "fail") return "fail";
      if (normalizeEdgeLabel(label) === "CONTINUE") return "continue";
      return undefined;
    case "start":
    case "action":
    case "end":
    case "annotation":
    default:
      return undefined;
  }
}

function resolveTargetHandle(targetType: DiagramNodeType | undefined, label?: string): string | undefined {
  const branch = getBranchClass(label);
  if (targetType === "decision") {
    return branch === "no" ? "top" : "left";
  }
  if (targetType === "end") {
    return branch === "no" || branch === "fail" ? "top" : "left";
  }
  return undefined;
}

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
    const branch = getBranchClass(e.label?.toString());
    if (branch === "forward") yesTarget.set(e.source, e.target);
    if (branch === "no") noTarget.set(e.source, e.target);
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
    if (rg === "rm_chain" || rg === "enf_chain" || rg === "authen_chain") return; // handled separately
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
    (n) =>
      (n.data.rank_group as string | undefined) === "rm_chain" ||
      (n.data.rank_group as string | undefined) === "authen_chain"
  );
  if (rmGroup.length >= 1) {
    rmGroup.sort((a, b) => a.position.x - b.position.x);
    const chainX = rmGroup[0].position.x;
    let y = rmGroup[0].position.y;
    let maxRightX = chainX;
    // Tracks the bottom y of all FAIL end nodes placed inline in the YES-column.
    // Used to push the terminal NO node (default auth rule) below them.
    let failEndBottomY = -Infinity;

    for (let i = 0; i < rmGroup.length; i++) {
      const chainNode = rmGroup[i];
      const h = chainNode.measured?.height ?? fallbackDecision.height;
      const w = chainNode.measured?.width  ?? fallbackDecision.width;
      chainNode.position = { x: chainX, y };

      // Bottom of any FAIL end node placed during this iteration (used to advance y).
      let procFailBottomY = -Infinity;

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

          if (actionNode.type === "process") {
            // authen_chain process node: place the FAIL end node directly below it
            // rather than via placeAdjacentRight (which would put it in the enf_chain
            // x-column, causing the overlap-resolution nudge loop to push it past the
            // terminal NO / default-rule process node that shares the same x-column).
            const failEdge = edges.find(
              (e) => e.source === actionId && e.label?.toString() === "FAIL"
            );
            if (failEdge) {
              const failNode = nodeById.get(failEdge.target);
              if (failNode) {
                const fnfb = NODE_SIZE_FALLBACKS[failNode.type ?? "end"] ?? { width: 130, height: 60 };
                const fnh = failNode.measured?.height ?? fnfb.height;
                const fnw = failNode.measured?.width  ?? fnfb.width;
                failNode.position = {
                  x: actionNode.position.x + (aw - fnw) / 2,
                  y: actionNode.position.y + ah + LABEL_GAP,
                };
                procFailBottomY = failNode.position.y + fnh;
                failEndBottomY = Math.max(failEndBottomY, procFailBottomY);
                maxRightX = Math.max(maxRightX, actionNode.position.x + fnw);
              }
            }
            // Still route any non-FAIL downstream through placeAdjacentRight (e.g. CONTINUE).
            (outEdges.get(actionId) ?? []).forEach((tid) => {
              if (failEdge && tid === failEdge.target) return; // already placed above
              placeAdjacentRight(actionNode, tid, actionRight);
            });
          } else {
            // rm_chain action nodes: original behaviour unchanged.
            (outEdges.get(actionId) ?? []).forEach((tid) =>
              placeAdjacentRight(actionNode, tid, actionRight)
            );
          }
        }
      }

      // Terminal NO node of the last decision (rm_default or no_role_end).
      // For authen_chain, push it below any FAIL end nodes placed in the YES-column.
      if (i === rmGroup.length - 1) {
        const termId = noTarget.get(chainNode.id);
        if (termId) {
          const term = nodeById.get(termId);
          if (term && !(term.data.rank_group as string | undefined)) {
            const tw = term.measured?.width
              ?? (NODE_SIZE_FALLBACKS[term.type ?? "action"]?.width ?? 160);
            const naturalTermY = y + h + VERT_GAP;
            const termY = failEndBottomY > -Infinity
              ? Math.max(naturalTermY, failEndBottomY + VERT_GAP)
              : naturalTermY;
            term.position = { x: chainX + w + ACTION_INSET, y: termY };
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

      // Advance y: ensure the next chain decision clears any FAIL end node placed
      // inline in this iteration (handles chains with N conditional rules).
      const naturalNextY = y + h + VERT_GAP;
      y = procFailBottomY > -Infinity
        ? Math.max(naturalNextY, procFailBottomY + VERT_GAP)
        : naturalNextY;
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

  // ---- Process FAIL exits: place FAIL end nodes below their process source ----
  // Match-all authen rules have no decision node so they are absent from rmGroup;
  // the FAIL placement inside the rmGroup loop never fires for them.  Run a
  // dedicated pass here so every process→FAIL end lands below its source node,
  // regardless of whether it was handled by chain logic above.
  result.forEach((node) => {
    if (node.type !== "process") return;
    const failEdge = edges.find(
      (e) => e.source === node.id && normalizeEdgeLabel(e.label?.toString()) === "FAIL"
    );
    if (!failEdge) return;
    const failNode = nodeById.get(failEdge.target);
    if (!failNode) return;
    const rg = failNode.data.rank_group as string | undefined;
    if (rg === "rm_chain" || rg === "enf_chain" || rg === "authen_chain") return;
    const nb = nodeBBox(node);
    const fnfb = NODE_SIZE_FALLBACKS[failNode.type ?? "end"] ?? { width: 130, height: 60 };
    const fnw = failNode.measured?.width ?? fnfb.width;
    failNode.position = {
      x: node.position.x + (nb.w - fnw) / 2,
      y: node.position.y + nb.h + LABEL_GAP,
    };
  });

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

    const newX = srcNode.position.x + (sb.w - nw) / 2;
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
  allServices: ServiceSummary[];
  fileRef: React.RefObject<File | null> | undefined;
  layoutReadyRef: React.RefObject<(() => void) | null>;
  layoutAppliedRef: React.RefObject<boolean>;
  onBatchFlowChange: (f: FlowIR | null) => void;
}

// Maximum total pixels for rasterised exports.  Keeps file size and memory
// usage reasonable even for very large diagrams.
const EXPORT_MAX_PIXELS = 64_000_000; // ~64 MP — allows pixelRatio ≥ 2 even for large diagrams
const EXPORT_PADDING    = 80;         // px padding around diagram in exports (extra room for edge curves)

/**
 * Composite a captured (potentially transparent) dataUrl onto a solid white
 * canvas.  html-to-image's backgroundColor option is applied to the target
 * element, not the canvas — so when the element is CSS-transformed the
 * background is offset and transparent pixels leak through.  Compositing here
 * fixes that by filling the full canvas first.
 */
async function applyBackground(
  dataUrl: string,
  widthPx: number,
  heightPx: number,
  mimeType: "image/png" | "image/jpeg",
  quality = 0.92,
): Promise<string> {
  const canvas = document.createElement("canvas");
  canvas.width = widthPx;
  canvas.height = heightPx;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, widthPx, heightPx);
  const img = new Image();
  img.src = dataUrl;
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("Failed to load capture for background compositing"));
  });
  ctx.drawImage(img, 0, 0);
  return canvas.toDataURL(mimeType, quality);
}

/** Compute the highest integer pixelRatio that stays within a pixel budget. */
function clampPixelRatio(
  logicalW: number,
  logicalH: number,
  desired: number,
  maxPixels: number,
): number {
  const ratio = Math.sqrt(maxPixels / (logicalW * logicalH));
  return Math.max(1, Math.min(desired, Math.floor(ratio)));
}

function ExportPanel({
  wrapperRef,
  serviceName,
  allServices,
  fileRef,
  layoutReadyRef,
  layoutAppliedRef,
  onBatchFlowChange,
}: ExportPanelProps) {
  const { getNodes, getEdges } = useReactFlow();
  const [exporting, setExporting] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [transparentBg, setTransparentBg] = useState(false);
  const [includeGrid, setIncludeGrid] = useState(false);
  const [batchExporting, setBatchExporting] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{ current: number; total: number } | null>(null);
  const [batchFormat, setBatchFormat] = useState<"png" | "svg" | "pdf" | "drawio">("png");

  /**
   * Capture the diagram by targeting .react-flow__viewport directly and
   * overriding its CSS transform to render at scale=1 with a tight
   * bounding box.  This makes the export independent of the user's
   * current pan/zoom and eliminates wasted whitespace.
   */
  const captureImage = useCallback(
    async (
      format: "png" | "svg" | "jpeg",
      transparent: boolean,
      withGrid: boolean,
      maxPixels: number,
    ): Promise<{ dataUrl: string; pixelRatio: number }> => {
      const viewportEl = wrapperRef.current!.querySelector(
        ".react-flow__viewport"
      ) as HTMLElement;
      if (!viewportEl) throw new Error("Could not find .react-flow__viewport");

      const nodes = getNodes();
      if (nodes.length === 0) throw new Error("No nodes to export");

      // Compute tight bounding box using per-type fallback sizes.
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const n of nodes) {
        const fb = NODE_SIZE_FALLBACKS[n.type ?? "process"] ?? { width: 160, height: 80 };
        const w = n.measured?.width ?? fb.width;
        const h = n.measured?.height ?? fb.height;
        minX = Math.min(minX, n.position.x);
        minY = Math.min(minY, n.position.y);
        maxX = Math.max(maxX, n.position.x + w);
        maxY = Math.max(maxY, n.position.y + h);
      }

      const imgW = Math.ceil(maxX - minX + EXPORT_PADDING * 2);
      const imgH = Math.ceil(maxY - minY + EXPORT_PADDING * 2);
      const pixelRatio = clampPixelRatio(imgW, imgH, 4, maxPixels);

      const options = {
        filter: (el: HTMLElement) => {
          const cl = el.classList;
          if (!cl) return true;
          return (
            !cl.contains("react-flow__panel") &&
            !cl.contains("react-flow__controls") &&
            (withGrid || !cl.contains("react-flow__background"))
          );
        },
        // No backgroundColor here — applying it to the translated viewport element
        // offsets the fill rect, leaving transparent strips that JPEG renders as black.
        // White background is composited at canvas level below (applyBackground).
        // SVG is the exception: html-to-image inserts a <rect>, which is unaffected
        // by the transform offset issue, so we pass it directly for SVG only.
        width: imgW,
        height: imgH,
        style: {
          width: `${imgW}px`,
          height: `${imgH}px`,
          transform: `translate(${-minX + EXPORT_PADDING}px, ${-minY + EXPORT_PADDING}px) scale(1)`,
        },
        pixelRatio,
      };

      if (format === "svg") {
        const dataUrl = await toSvg(viewportEl, {
          ...options,
          ...(transparent ? {} : { backgroundColor: "#ffffff" }),
        });
        return { dataUrl, pixelRatio };
      }

      // Always capture as transparent PNG. Using toJpeg here would encode
      // transparent pixels as black *before* applyBackground can add the white
      // fill, causing a black background on the output.
      const rawDataUrl = await toPng(viewportEl, options);

      // JPEG has no alpha channel; non-transparent PNG also needs a white fill.
      // Composite onto a white canvas to guarantee a clean, full-coverage background.
      const needsWhite = !transparent || format === "jpeg";
      if (needsWhite) {
        const mime = format === "jpeg" ? "image/jpeg" : "image/png";
        const dataUrl = await applyBackground(rawDataUrl, imgW * pixelRatio, imgH * pixelRatio, mime, 0.92);
        return { dataUrl, pixelRatio };
      }

      return { dataUrl: rawDataUrl, pixelRatio };
    },
    [getNodes, wrapperRef]
  );

  const download = useCallback((dataUrl: string, filename: string) => {
    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = filename;
    a.click();
  }, []);

  const handleExportPng = useCallback(async () => {
    if (exporting || !wrapperRef.current) return;
    setExporting(true);
    try {
      const { dataUrl } = await captureImage("png", transparentBg, includeGrid, EXPORT_MAX_PIXELS);
      download(dataUrl, `${serviceName}.png`);
    } finally {
      setExporting(false);
    }
  }, [exporting, captureImage, serviceName, transparentBg, includeGrid, wrapperRef, download]);

  const handleExportSvg = useCallback(async () => {
    if (exporting || !wrapperRef.current) return;
    setExporting(true);
    try {
      const { dataUrl } = await captureImage("svg", transparentBg, includeGrid, EXPORT_MAX_PIXELS);
      download(dataUrl, `${serviceName}.svg`);
    } finally {
      setExporting(false);
    }
  }, [exporting, captureImage, serviceName, transparentBg, includeGrid, wrapperRef, download]);

  const handleExportPdf = useCallback(async () => {
    if (exporting || !wrapperRef.current) return;
    setExporting(true);
    try {
      // Use JPEG for PDF — dramatically smaller file size vs PNG with no visible quality loss.
      // JPEG has no alpha channel, so transparentBg is intentionally ignored here.
      const { dataUrl, pixelRatio } = await captureImage("jpeg", false, includeGrid, EXPORT_MAX_PIXELS);
      const img = new Image();
      img.src = dataUrl;
      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = () => reject(new Error("Failed to decode exported image"));
      });
      const pdfW = img.width / pixelRatio;
      const pdfH = img.height / pixelRatio;
      const pdf = new jsPDF({
        orientation: pdfW > pdfH ? "landscape" : "portrait",
        unit: "px",
        format: [pdfW, pdfH],
      });
      pdf.addImage(dataUrl, "JPEG", 0, 0, pdfW, pdfH);
      pdf.save(`${serviceName}.pdf`);
    } finally {
      setExporting(false);
    }
  }, [exporting, captureImage, serviceName, transparentBg, includeGrid, wrapperRef, download]);

  const handleExportDrawio = useCallback(() => {
    const nodes = getNodes();
    const edges = getEdges();

    const xmlAttr = (s: string) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

    const styleMap: Record<string, string> = {
      start:      "ellipse;whiteSpace=wrap;html=1;",
      decision:   "rhombus;whiteSpace=wrap;html=1;",
      process:    "rounded=0;whiteSpace=wrap;html=1;",
      action:     "rounded=1;arcSize=12;whiteSpace=wrap;html=1;",
      end:        "ellipse;whiteSpace=wrap;html=1;strokeWidth=3;",
      annotation: "text;html=1;strokeColor=none;align=left;verticalAlign=top;whiteSpace=wrap;overflow=hidden;",
    };

    const cells: string[] = [
      '<mxCell id="0"/>',
      '<mxCell id="1" parent="0"/>',
    ];

    for (const n of nodes) {
      const w = n.measured?.width  ?? 180;
      const h = n.measured?.height ?? 80;
      const x = n.position.x;
      const y = n.position.y;
      const ntype = n.type ?? "process";
      const fill = (n.data as Record<string, unknown>)?.color as string | undefined;
      const baseStyle = styleMap[ntype] ?? styleMap.process;
      const style = fill ? `${baseStyle}fillColor=${fill};` : baseStyle;
      const label = xmlAttr(String((n.data as Record<string, unknown>)?.label ?? "").replace(/\n/g, "<br>"));
      cells.push(
        `<mxCell id="${n.id}" value="${label}" vertex="1" parent="1" style="${style}">` +
        `<mxGeometry x="${x}" y="${y}" width="${w}" height="${h}" as="geometry"/>` +
        `</mxCell>`
      );
    }

    for (const e of edges) {
      const label = xmlAttr(String((e.data as Record<string, unknown>)?.label ?? e.label ?? ""));
      cells.push(
        `<mxCell id="${e.id}" value="${label}" edge="1" source="${e.source}" target="${e.target}" parent="1">` +
        `<mxGeometry relative="1" as="geometry"/>` +
        `</mxCell>`
      );
    }

    const xml =
      `<?xml version="1.0" encoding="UTF-8"?>\n` +
      `<mxGraphModel><root>${cells.join("")}</root></mxGraphModel>`;

    const blob = new Blob([xml], { type: "application/xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${serviceName}.drawio`;
    a.click();
    URL.revokeObjectURL(url);
  }, [getNodes, getEdges, serviceName]);

  const handleExportAll = useCallback(async () => {
    if (batchExporting || exporting || !fileRef?.current || allServices.length < 2) return;

    const { default: JSZip } = await import("jszip");
    const zip = new JSZip();
    const fileBaseName = fileRef.current.name.replace(/\.[^.]+$/, "");
    const seenNames = new Set<string>();
    const failed: string[] = [];

    // Draw.io XML generation helper — duplicated from handleExportDrawio so it
    // can run inside the loop using the post-layout getNodes/getEdges snapshot.
    const buildDrawioXml = () => {
      const nodes = getNodes();
      const edges = getEdges();
      const xmlAttr = (s: string) =>
        s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const styleMap: Record<string, string> = {
        start:      "ellipse;whiteSpace=wrap;html=1;",
        decision:   "rhombus;whiteSpace=wrap;html=1;",
        process:    "rounded=0;whiteSpace=wrap;html=1;",
        action:     "rounded=1;arcSize=12;whiteSpace=wrap;html=1;",
        end:        "ellipse;whiteSpace=wrap;html=1;strokeWidth=3;",
        annotation: "text;html=1;strokeColor=none;align=left;verticalAlign=top;whiteSpace=wrap;overflow=hidden;",
      };
      const cells: string[] = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>'];
      for (const n of nodes) {
        const w = n.measured?.width ?? 180, h = n.measured?.height ?? 80;
        const ntype = n.type ?? "process";
        const fill = (n.data as Record<string, unknown>)?.color as string | undefined;
        const style = fill ? `${styleMap[ntype] ?? styleMap.process}fillColor=${fill};` : (styleMap[ntype] ?? styleMap.process);
        const label = xmlAttr(String((n.data as Record<string, unknown>)?.label ?? "").replace(/\n/g, "<br>"));
        cells.push(
          `<mxCell id="${n.id}" value="${label}" vertex="1" parent="1" style="${style}">` +
          `<mxGeometry x="${n.position.x}" y="${n.position.y}" width="${w}" height="${h}" as="geometry"/>` +
          `</mxCell>`
        );
      }
      for (const e of edges) {
        const label = xmlAttr(String((e.data as Record<string, unknown>)?.label ?? e.label ?? ""));
        cells.push(
          `<mxCell id="${e.id}" value="${label}" edge="1" source="${e.source}" target="${e.target}" parent="1">` +
          `<mxGeometry relative="1" as="geometry"/></mxCell>`
        );
      }
      return `<?xml version="1.0" encoding="UTF-8"?>\n<mxGraphModel><root>${cells.join("")}</root></mxGraphModel>`;
    };

    setBatchExporting(true);

    for (let i = 0; i < allServices.length; i++) {
      const svc = allServices[i];
      setBatchProgress({ current: i + 1, total: allServices.length });
      try {
        const flowData = await fetchFlow(fileRef.current, svc.id);
        layoutAppliedRef.current = false;
        onBatchFlowChange(flowData);
        await waitForLayout(layoutReadyRef);
        // Small buffer for React to paint after fitView.
        await new Promise<void>((r) => setTimeout(r, 100));

        let name = svc.name.replace(/[^a-zA-Z0-9_\-. ]/g, "_").trim() || "service";
        if (seenNames.has(name)) name = `${name}_${i}`;
        seenNames.add(name);

        if (batchFormat === "png") {
          const { dataUrl } = await captureImage("png", false, false, EXPORT_MAX_PIXELS);
          zip.file(`${name}.png`, dataUrl.split(",")[1], { base64: true });
        } else if (batchFormat === "svg") {
          const { dataUrl } = await captureImage("svg", false, false, EXPORT_MAX_PIXELS);
          // toSvg returns a URL-encoded data URL, not base64 — decode to raw SVG text.
          const svgText = decodeURIComponent(dataUrl.split(",").slice(1).join(","));
          zip.file(`${name}.svg`, svgText);
        } else if (batchFormat === "pdf") {
          const { dataUrl, pixelRatio } = await captureImage("jpeg", false, false, EXPORT_MAX_PIXELS);
          const img = new Image();
          img.src = dataUrl;
          await new Promise<void>((resolve, reject) => { img.onload = () => resolve(); img.onerror = () => reject(new Error("img load failed")); });
          const pdfW = img.width / pixelRatio;
          const pdfH = img.height / pixelRatio;
          const pdf = new jsPDF({ orientation: pdfW > pdfH ? "landscape" : "portrait", unit: "px", format: [pdfW, pdfH] });
          pdf.addImage(dataUrl, "JPEG", 0, 0, pdfW, pdfH);
          zip.file(`${name}.pdf`, pdf.output("blob"));
        } else {
          // drawio
          zip.file(`${name}.drawio`, buildDrawioXml());
        }
      } catch {
        failed.push(svc.name);
      }
    }

    onBatchFlowChange(null);
    setBatchExporting(false);
    setBatchProgress(null);

    if (Object.keys(zip.files).length === 0) {
      console.error("Export All: all services failed", failed);
      return;
    }

    const blob = await zip.generateAsync({ type: "blob" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${fileBaseName}-all-services.zip`;
    a.click();
    URL.revokeObjectURL(url);
  }, [
    batchExporting, exporting, fileRef, batchFormat, allServices,
    captureImage, layoutReadyRef, layoutAppliedRef, onBatchFlowChange,
    getNodes, getEdges,
  ]);

  return (
    <>
    {batchExporting && batchProgress && (
      <div style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
        zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <div style={{
          background: "#1f2937", borderRadius: 10, padding: "28px 40px",
          textAlign: "center", minWidth: 260, color: "#fff",
          fontFamily: "Helvetica, Arial, sans-serif",
          boxShadow: "0 4px 24px rgba(0,0,0,0.4)",
        }}>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 12 }}>
            Exporting All Services…
          </div>
          <div style={{ fontSize: 14, color: "#d1d5db", marginBottom: 16 }}>
            {batchProgress.current} of {batchProgress.total}
          </div>
          <div style={{ height: 6, background: "#374151", borderRadius: 3, overflow: "hidden" }}>
            <div style={{
              height: "100%", background: "#3b82f6", borderRadius: 3,
              width: `${(batchProgress.current / batchProgress.total) * 100}%`,
              transition: "width 0.2s ease",
            }} />
          </div>
        </div>
      </div>
    )}
    <Panel position="top-right">
      <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
        <button onClick={() => setMenuOpen((o) => !o)} disabled={exporting}>
          {exporting ? "Exporting…" : `Export ${menuOpen ? "▲" : "▼"}`}
        </button>
        {menuOpen && (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "stretch" }}>
              <button onClick={handleExportPng} disabled={exporting}>PNG</button>
              <button onClick={handleExportSvg} disabled={exporting}>SVG</button>
              <button onClick={handleExportPdf} disabled={exporting}>PDF</button>
              <button
                onClick={handleExportDrawio}
                disabled={exporting}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}
              >
                <span>Draw.io</span>
                <span style={{
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: "0.03em",
                  background: "#f59e0b",
                  color: "#fff",
                  borderRadius: 3,
                  padding: "1px 4px",
                  lineHeight: 1.4,
                }}>BETA</span>
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
            <label style={{ fontSize: 11, color: "#555", cursor: "pointer", userSelect: "none" }}>
              <input
                type="checkbox"
                checked={includeGrid}
                onChange={(e) => setIncludeGrid(e.target.checked)}
                style={{ marginRight: 4 }}
              />
              Include grid dots
            </label>
            {allServices.length > 1 && (
              <>
                <div style={{ borderTop: "1px solid #e5e7eb", margin: "4px 0" }} />
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <div style={{ display: "flex", gap: 4 }}>
                    {(["png", "svg"] as const).map((f) => (
                      <button
                        key={f}
                        onClick={() => setBatchFormat(f)}
                        style={{
                          flex: 1,
                          fontWeight: batchFormat === f ? 700 : 400,
                          background: batchFormat === f ? "#dbeafe" : undefined,
                        }}
                      >
                        {f.toUpperCase()}
                      </button>
                    ))}
                  </div>
                  <div style={{ display: "flex", gap: 4 }}>
                    {(["pdf", "drawio"] as const).map((f) => (
                      <button
                        key={f}
                        onClick={() => setBatchFormat(f)}
                        style={{
                          flex: 1,
                          fontWeight: batchFormat === f ? 700 : 400,
                          background: batchFormat === f ? "#dbeafe" : undefined,
                        }}
                      >
                        {f === "drawio" ? "Draw.io" : f.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>
                <button
                  onClick={handleExportAll}
                  disabled={exporting || batchExporting}
                >
                  {batchExporting
                    ? `Exporting ${batchProgress?.current ?? 0}/${batchProgress?.total ?? allServices.length}…`
                    : "Export All (ZIP)"}
                </button>
              </>
            )}
          </>
        )}
      </div>
    </Panel>
    </>
  );
}

// ---------------------------------------------------------------------------
// AnnotationPanel — "Add Note" + "Snap" toggle; rendered inside <ReactFlow>
// ---------------------------------------------------------------------------

interface AnnotationPanelProps {
  nodeColors: NodeColors;
}

function AnnotationPanel({ nodeColors }: AnnotationPanelProps) {
  const { screenToFlowPosition, setNodes } = useReactFlow();

  const addAnnotation = useCallback(() => {
    const pos = screenToFlowPosition({
      x: window.innerWidth / 2,
      y: window.innerHeight / 2,
    });
    setNodes((nds) => [
      ...nds,
      {
        id: crypto.randomUUID(),
        type: "annotation",
        position: pos,
        data: { text: "", colors: nodeColors },
        style: { width: 220, height: 100 },
      },
    ]);
  }, [screenToFlowPosition, setNodes, nodeColors]);

  return (
    <Panel position="top-left">
      <button onClick={addAnnotation}>Add Note</button>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// SelectionHintPanel — dismissable multi-select tip; rendered inside <ReactFlow>
// ---------------------------------------------------------------------------

function SelectionHintPanel() {
  const [visible, setVisible] = useState(
    () => !localStorage.getItem("multiSelectHintDismissed")
  );

  const dismiss = () => {
    localStorage.setItem("multiSelectHintDismissed", "1");
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <Panel position="bottom-center">
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        background: "#fff", border: "1px solid #d1d5db",
        borderRadius: 6, padding: "6px 10px", fontSize: 12, color: "#555",
        boxShadow: "0 1px 4px rgba(0,0,0,0.1)",
      }}>
        <span>
          Tip: <strong>Shift+click</strong> or <strong>drag the canvas</strong> to
          select multiple nodes, then drag to move as a group.
        </span>
        <button
          onClick={dismiss}
          style={{ background: "none", border: "none", cursor: "pointer",
                   fontSize: 14, color: "#999", lineHeight: 1, padding: 0 }}
          aria-label="Dismiss"
        >
          ✕
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
  diamondScale: number;
  setDiamondScale: (scale: number) => void;
}

const NODE_COLOR_LABELS: { key: keyof NodeColors; label: string }[] = [
  { key: "start",      label: "Start" },
  { key: "decision",   label: "Decision" },
  { key: "process",    label: "Process" },
  { key: "action",     label: "Action" },
  { key: "end",        label: "End" },
  { key: "annotation", label: "Annotation" },
];

function StylePanel({ nodeColors, setNodeColors, diamondScale, setDiamondScale }: StylePanelProps) {
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
        <div style={{ borderTop: "1px solid #e5e7eb", marginTop: 4, paddingTop: 6 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#333", marginBottom: 3 }}>
            Diamond Size
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="range"
              min={1}
              max={1.5}
              step={0.1}
              value={diamondScale}
              onChange={(e) => setDiamondScale(parseFloat(e.target.value))}
              style={{ width: 90 }}
            />
            <span style={{ fontSize: 11, color: "#555", minWidth: 32 }}>
              {Math.round(diamondScale * 100)}%
            </span>
          </div>
        </div>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------

interface LayoutEffectProps {
  layoutAppliedRef: React.RefObject<boolean>;
  layoutReadyRef: React.RefObject<(() => void) | null>;
  layoutTrigger: number;
}

/** Rendered inside <ReactFlow> so it can use React Flow context hooks. */
function LayoutEffect({ layoutAppliedRef, layoutReadyRef, layoutTrigger }: LayoutEffectProps) {
  const nodesInitialized = useNodesInitialized();
  const { setNodes, fitView, getEdges } = useReactFlow();

  useEffect(() => {
    if (!nodesInitialized || layoutAppliedRef.current) return;
    const edges = getEdges();
    setNodes((nds) => applyDagreLayout(nds, edges));
    layoutAppliedRef.current = true;
    // Brief delay to let React Flow commit the position update before fitting the view.
    setTimeout(() => {
      fitView({ padding: 0.15 });
      // Signal batch export (if active) that layout is complete.
      if (layoutReadyRef.current) {
        layoutReadyRef.current();
        layoutReadyRef.current = null;
      }
    }, 50);
  }, [nodesInitialized, layoutTrigger, getEdges, setNodes, fitView, layoutAppliedRef, layoutReadyRef]);

  return null;
}

/** Promise that resolves when dagre layout completes, with a 3 s safety timeout. */
function waitForLayout(layoutReadyRef: React.RefObject<(() => void) | null>): Promise<void> {
  return new Promise((resolve) => {
    layoutReadyRef.current = resolve;
    setTimeout(resolve, 3000);
  });
}

// ---------------------------------------------------------------------------
// KeyboardHandler — copy/paste for annotation nodes; rendered inside <ReactFlow>
// so it has access to useReactFlow() (screenToFlowPosition, getNodes, etc.)
// ---------------------------------------------------------------------------

interface KeyboardHandlerProps {
  serviceId: string;
  localClipboardRef: React.RefObject<AnnotationClipboard | null>;
  contextClipboardRef: React.RefObject<AnnotationClipboard | null>;
  sessionDispatch: ReturnType<typeof useDiagramSession>["dispatch"];
}

function KeyboardHandler({
  serviceId,
  localClipboardRef,
  contextClipboardRef,
  sessionDispatch,
}: KeyboardHandlerProps) {
  const { screenToFlowPosition, getNodes, getEdges, setNodes, setEdges } = useReactFlow();

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const platform =
        (navigator as Navigator & { userAgentData?: { platform?: string } })
          .userAgentData?.platform ?? navigator.userAgent;
      const isMac = /mac/i.test(platform);
      const mod = isMac ? e.metaKey : e.ctrlKey;
      if (!mod) return;
      if (e.key !== "c" && e.key !== "v") return;

      // Tiptap guard: if focus is inside a ProseMirror editor, let the browser
      // handle text copy/paste normally.
      const ae = document.activeElement;
      if (ae && ae.closest(".ProseMirror")) return;

      if (e.key === "c") {
        const nodes = getNodes();
        const selectedAnnotations = nodes.filter(
          (n) => n.selected && n.type === "annotation"
        );
        if (selectedAnnotations.length === 0) return;
        e.preventDefault();

        const idMap = new Map<string, string>();
        const newNodes: Node[] = selectedAnnotations.map((n) => {
          const newId = crypto.randomUUID();
          idMap.set(n.id, newId);
          return { ...n, id: newId };
        });

        const edges = getEdges();
        const newEdges: Edge[] = edges
          .filter(
            (ed) =>
              (ed.data as Record<string, unknown>)?.isAnnotation &&
              idMap.has(ed.source) &&
              idMap.has(ed.target)
          )
          .map((ed) => ({
            ...ed,
            id: crypto.randomUUID(),
            source: idMap.get(ed.source)!,
            target: idMap.get(ed.target)!,
          }));

        const payload: AnnotationClipboard = {
          nodes: newNodes,
          edges: newEdges,
          sourceServiceId: serviceId,
        };
        localClipboardRef.current = payload;
        sessionDispatch({ type: "SET_CLIPBOARD", payload });
      } else if (e.key === "v") {
        const clipboard = localClipboardRef.current ?? contextClipboardRef.current;
        if (!clipboard || clipboard.nodes.length === 0) return;
        e.preventDefault();

        const isSameService = clipboard.sourceServiceId === serviceId;

        // Anchor position for cross-diagram paste: flow coords at viewport center.
        let anchorPos = { x: 0, y: 0 };
        if (!isSameService) {
          anchorPos = screenToFlowPosition({
            x: window.innerWidth / 2,
            y: window.innerHeight / 2,
          });
        }

        // Relative offset from the first copied node's position (preserves group layout).
        const originPos = clipboard.nodes[0].position;

        const idMap = new Map<string, string>();
        const newNodes: Node[] = clipboard.nodes.map((n) => {
          const newId = crypto.randomUUID();
          idMap.set(n.id, newId);
          const position = isSameService
            ? { x: n.position.x + 20, y: n.position.y + 20 }
            : {
                x: anchorPos.x + (n.position.x - originPos.x),
                y: anchorPos.y + (n.position.y - originPos.y),
              };
          return { ...n, id: newId, position, selected: false };
        });

        // Keep only edges whose both endpoints were in the copied set.
        // Drop edges to diagram nodes (those IDs won't exist in another service).
        const newEdges: Edge[] = clipboard.edges
          .filter((ed) => idMap.has(ed.source) && idMap.has(ed.target))
          .map((ed) => ({
            ...ed,
            id: crypto.randomUUID(),
            source: idMap.get(ed.source)!,
            target: idMap.get(ed.target)!,
          }));

        setNodes((nds) => [...nds, ...newNodes]);
        setEdges((eds) => [...eds, ...newEdges]);
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [
    serviceId,
    localClipboardRef,
    contextClipboardRef,
    sessionDispatch,
    screenToFlowPosition,
    getNodes,
    getEdges,
    setNodes,
    setEdges,
  ]);

  return null;
}

// ---------------------------------------------------------------------------

interface Props {
  flow: FlowIR;
  allServices?: ServiceSummary[];
  fileRef?: React.RefObject<File | null>;
}

export default function FlowDiagram({ flow, allServices = [], fileRef }: Props) {
  const { state: sessionState, dispatch: sessionDispatch } = useDiagramSession();
  const diamondScale = sessionState.diamondScale;
  const setDiamondScale = (scale: number) =>
    sessionDispatch({ type: "SET_DIAMOND_SCALE", scale });
  const serviceId = flow.service_id;

  const flowWrapperRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const layoutAppliedRef = useRef(false);
  const layoutReadyRef = useRef<(() => void) | null>(null);

  // During batch export, temporarily override the displayed flow without changing the prop.
  const [batchFlow, setBatchFlow] = useState<FlowIR | null>(null);
  const [layoutTrigger, setLayoutTrigger] = useState(0);
  const activeFlow = batchFlow ?? flow;
  const [nodeColors, setNodeColors] = useState<NodeColors>(DEFAULT_NODE_COLORS);
  // Ref so the flow-load effect always uses the current colors without re-running layout.
  const nodeColorsRef = useRef(nodeColors);
  useEffect(() => {
    nodeColorsRef.current = nodeColors;
  }, [nodeColors]);

  // Keep a ref to sessionState so the load effect can read saved annotations without
  // adding sessionState to its dependency array (which would cause re-layout on every
  // annotation change).
  const sessionStateRef = useRef(sessionState);
  sessionStateRef.current = sessionState;

  // Local clipboard ref (fastest path for within-diagram paste).
  // Also mirrors to context via SET_CLIPBOARD for cross-diagram paste.
  const localClipboardRef = useRef<AnnotationClipboard | null>(null);

  // contextClipboardRef lets KeyboardHandler read context.clipboard without it
  // being a reactive dependency.
  const contextClipboardRef = useRef<AnnotationClipboard | null>(sessionState.clipboard);
  contextClipboardRef.current = sessionState.clipboard;

  // Debounced save: persist annotation nodes/edges + nodeColors to session context
  // ~300 ms after the last change (avoids excessive dispatches during drag).
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      const editState: DiagramEditState = {
        annotationNodes: nodes.filter((n) => n.type === "annotation"),
        annotationEdges: edges.filter((e) => (e.data as Record<string, unknown>)?.isAnnotation),
        nodeColors,
      };
      sessionDispatch({ type: "SAVE_EDIT_STATE", serviceId, state: editState });
    }, 300);
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [nodes, edges, nodeColors, serviceId, sessionDispatch]);

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
            id: crypto.randomUUID(),
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

  // Callback for ExportPanel to swap the displayed flow during batch export.
  const handleBatchFlowChange = useCallback((f: FlowIR | null) => {
    layoutAppliedRef.current = false;
    setBatchFlow(f);
  }, []);

  // Propagate color changes to all existing nodes (including user-placed annotations).
  useEffect(() => {
    setNodes((nds) => nds.map((n) => ({ ...n, data: { ...n.data, colors: nodeColors } })));
  }, [nodeColors, setNodes]);

  // Propagate diamond scale changes and re-run dagre with new measured dimensions.
  // The setTimeout gives React Flow's ResizeObserver time to update node.measured
  // before LayoutEffect fires — without it dagre would lay out with stale sizes.
  useEffect(() => {
    setNodes((nds) => nds.map((n) => ({ ...n, data: { ...n.data, diamondScale } })));
    layoutAppliedRef.current = false;
    const id = setTimeout(() => setLayoutTrigger((t) => t + 1), 100);
    return () => clearTimeout(id);
  }, [diamondScale, setNodes]);

  useEffect(() => {
    const rawNodes: Node[] = activeFlow.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      data: {
        label: n.label,
        sub_label: n.sub_label,
        trace_rule_id: n.trace_rule_id,
        rank_group: n.rank_group,
        colors: nodeColorsRef.current,
        diamondScale: sessionStateRef.current.diamondScale,
      },
      position: { x: 0, y: 0 },
    }));

    const nodeTypeById = new Map(activeFlow.nodes.map((n) => [n.id, n.type]));
    const rawEdges: Edge[] = activeFlow.edges.map((e, i) => {
      const isContinue = normalizeEdgeLabel(e.label) === "CONTINUE";
      const displayLabel = isContinue && e.reason
        ? `CONTINUE (${e.reason})`
        : (e.label || undefined);
      return {
        id: `edge-${i}`,
        type: "smoothstep",
        source: e.from_id,
        target: e.to_id,
        sourceHandle: resolveSourceHandle(nodeTypeById.get(e.from_id), e.label),
        targetHandle: resolveTargetHandle(nodeTypeById.get(e.to_id), e.label),
        label: displayLabel,
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12 },
        style: isContinue
          ? { stroke: "#888", strokeWidth: 1.5, strokeDasharray: "5,3" }
          : { stroke: "#555", strokeWidth: 1.5 },
        labelStyle: { fontSize: 10, fontFamily: "Helvetica, Arial, sans-serif" },
        labelBgStyle: { fill: "#fff", fillOpacity: 0.8 },
      };
    });

    // During batch export skip annotation restore — only restore for the real selected flow.
    const saved = batchFlow ? null : sessionStateRef.current.editStates[activeFlow.service_id];
    if (saved) {
      setNodes([...rawNodes, ...saved.annotationNodes]);
      setEdges([...rawEdges, ...saved.annotationEdges]);
      setNodeColors(saved.nodeColors);
    } else {
      setNodes(rawNodes);
      setEdges(rawEdges);
    }
    layoutAppliedRef.current = false; // Reset so layout runs again when a new flow loads.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFlow, setNodes, setEdges]);

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
      >
        <Background gap={16} color="#e5e7eb" />
        <Controls />
        <AnnotationPanel
          nodeColors={nodeColors}
        />
        <SelectionHintPanel />
        <StylePanel
          nodeColors={nodeColors}
          setNodeColors={setNodeColors}
          diamondScale={diamondScale}
          setDiamondScale={setDiamondScale}
        />
        <LayoutEffect
          layoutAppliedRef={layoutAppliedRef}
          layoutReadyRef={layoutReadyRef}
          layoutTrigger={layoutTrigger}
        />
        <KeyboardHandler
          serviceId={serviceId}
          localClipboardRef={localClipboardRef}
          contextClipboardRef={contextClipboardRef}
          sessionDispatch={sessionDispatch}
        />
        <ExportPanel
          wrapperRef={flowWrapperRef}
          serviceName={flow.service_name}
          allServices={allServices}
          fileRef={fileRef}
          layoutReadyRef={layoutReadyRef}
          layoutAppliedRef={layoutAppliedRef}
          onBatchFlowChange={handleBatchFlowChange}
        />
      </ReactFlow>
    </div>
  );
}
