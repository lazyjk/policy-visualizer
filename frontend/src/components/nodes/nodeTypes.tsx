/**
 * Custom React Flow node types.
 * Default colors match the existing Graphviz renderer in src/renderer.py.
 * Node fill colors are user-configurable via the StylePanel (per shape).
 */
import React, { useState } from "react";
import { Handle, Position, type NodeProps, NodeToolbar, useReactFlow } from "@xyflow/react";

export interface NodeColors {
  start: string;
  decision: string;
  process: string;
  action: string;
  end: string;
  annotation: string;
}

export const DEFAULT_NODE_COLORS: NodeColors = {
  start:      "#AED6F1",
  decision:   "#FAD7A0",
  process:    "#A9DFBF",
  action:     "#D7BDE2",
  end:        "#F1948A",
  annotation: "#FFFDE7",
};

interface NodeData {
  label: string;
  sub_label?: string;
  colors?: NodeColors;
  [key: string]: unknown;
}

function multilineLabel(label: string) {
  return label.split("\n").map((line, i) => (
    <React.Fragment key={i}>
      {i > 0 && <br />}
      {line}
    </React.Fragment>
  ));
}

// Number of label lines shown inside the diamond before truncating.
// Single-predicate conditions (3–4 lines) fit; multi-predicate ones get a tooltip.
const DIAMOND_LABEL_THRESHOLD = 4;

function truncateLines(label: string, maxLines: number): { display: string; overflow: number } {
  const lines = label.split("\n");
  if (lines.length <= maxLines) return { display: label, overflow: 0 };
  return { display: lines.slice(0, maxLines).join("\n"), overflow: lines.length - maxLines };
}

const tooltipStyle: React.CSSProperties = {
  background: "white",
  border: "1px solid #ccc",
  borderRadius: 6,
  padding: "8px 12px",
  fontSize: 11,
  fontFamily: "Helvetica, Arial, sans-serif",
  lineHeight: 1.4,
  boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
  maxWidth: 280,
  wordBreak: "break-word",
  pointerEvents: "none",
};

const baseStyle: React.CSSProperties = {
  fontSize: 11,
  fontFamily: "Helvetica, Arial, sans-serif",
  textAlign: "center",
  padding: "6px 10px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  lineHeight: 1.4,
  minWidth: 90,
  maxWidth: 200,
  wordBreak: "break-word",
  overflow: "hidden",
};

// start — ellipse
export function StartNode({ data }: NodeProps) {
  const d = data as NodeData;
  const fill = d.colors?.start ?? DEFAULT_NODE_COLORS.start;
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: fill,
        borderRadius: "50%",
        border: "2px solid #5DADE2",
        padding: "10px 14px",
      }}
    >
      <Handle type="source" position={Position.Right} />
      <div>{multilineLabel(d.label)}</div>
    </div>
  );
}

// decision — diamond (rotated square)
// Outer container is fixed at 220×220 to match NODE_SIZE_FALLBACKS in FlowDiagram.tsx.
// Inner square is 150×150; rotated 45° its bounding box is ~212px, which fits inside.
// overflow:hidden on the inner div clips text to the diamond shape.
// When the label exceeds DIAMOND_LABEL_THRESHOLD lines, the overflow is truncated and
// a styled NodeToolbar tooltip reveals the full condition on hover.
export function DecisionNode({ data }: NodeProps) {
  const d = data as NodeData;
  const [hovered, setHovered] = useState(false);
  const { display, overflow } = truncateLines(d.label, DIAMOND_LABEL_THRESHOLD);
  const isTruncated = overflow > 0;
  const fill = d.colors?.decision ?? DEFAULT_NODE_COLORS.decision;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: "relative",
        width: 220,
        height: 220,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {isTruncated && (
        <NodeToolbar isVisible={hovered} position={Position.Right}>
          <div style={tooltipStyle}>{multilineLabel(d.label)}</div>
        </NodeToolbar>
      )}
      <Handle type="target" position={Position.Left} id="left" />
      <Handle type="target" position={Position.Top} id="top" />
      <div
        style={{
          background: fill,
          border: "2px solid #E59866",
          transform: "rotate(45deg)",
          width: 150,
          height: 150,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            transform: "rotate(-45deg)",
            textAlign: "center",
            fontSize: 10,
            fontFamily: "Helvetica, Arial, sans-serif",
            lineHeight: 1.3,
            maxWidth: 130,
            wordBreak: "break-word",
            padding: "4px",
          }}
        >
          {multilineLabel(display)}
          {isTruncated && (
            <div style={{ fontSize: 9, opacity: 0.65, marginTop: 2 }}>+{overflow} more…</div>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="yes" />
      <Handle type="source" position={Position.Bottom} id="no" />
    </div>
  );
}

// process — plain rectangle
export function ProcessNode({ data }: NodeProps) {
  const d = data as NodeData;
  const fill = d.colors?.process ?? DEFAULT_NODE_COLORS.process;
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: fill,
        border: "2px solid #52BE80",
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div>{multilineLabel(d.label)}</div>
      <Handle type="source" position={Position.Right} />
      <Handle type="source" position={Position.Bottom} id="fail" />
    </div>
  );
}

// action — rounded rectangle
export function ActionNode({ data }: NodeProps) {
  const d = data as NodeData;
  const fill = d.colors?.action ?? DEFAULT_NODE_COLORS.action;
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: fill,
        border: "2px solid #A569BD",
        borderRadius: 12,
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div>{multilineLabel(d.label)}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

// end — double circle
export function EndNode({ data }: NodeProps) {
  const d = data as NodeData;
  const fill = d.colors?.end ?? DEFAULT_NODE_COLORS.end;
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: fill,
        border: "4px double #E74C3C",
        borderRadius: "50%",
        padding: "10px 14px",
      }}
    >
      <Handle type="target" position={Position.Left} id="left" />
      <Handle type="target" position={Position.Top} id="top" />
      <div>
        {multilineLabel(d.label)}
        {d.sub_label && (
          <>
            <br />
            <span style={{ fontSize: 9, opacity: 0.8 }}>{d.sub_label}</span>
          </>
        )}
      </div>
    </div>
  );
}

// annotation — sticky note with inline editing and connectable handles on all sides
// TODO(wysiwyg): Replace plain textarea edit mode with a lightweight WYSIWYG editor
// (bold, italic, bullet lists) — targeted post-2.0.0 GA. See ANN-223 in release-map-2.0.md.
export function AnnotationNode({ data, id }: NodeProps) {
  const d = data as { text?: string; colors?: NodeColors };
  const fill = d.colors?.annotation ?? DEFAULT_NODE_COLORS.annotation;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const { updateNodeData } = useReactFlow();

  const startEdit = () => {
    setDraft(d.text ?? "");
    setEditing(true);
  };

  const commit = () => {
    updateNodeData(id, { text: draft });
    setEditing(false);
  };

  return (
    <div
      onDoubleClick={startEdit}
      style={{
        background: fill,
        border: "2px dashed #F9A825",
        borderRadius: 6,
        padding: "8px 10px",
        minWidth: 140,
        minHeight: 60,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "flex-start",
        position: "relative",
        boxShadow: "0 1px 4px rgba(0,0,0,0.12)",
      }}
    >
      <Handle type="source" position={Position.Top} id="top" />
      <Handle type="source" position={Position.Right} id="right" />
      <Handle type="source" position={Position.Bottom} id="bottom" />
      <Handle type="source" position={Position.Left} id="left" />
      {editing ? (
        <textarea
          className="nodrag"
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setEditing(false);
            }
          }}
          style={{
            border: "none",
            background: "transparent",
            resize: "none",
            fontFamily: "Helvetica, Arial, sans-serif",
            fontSize: 12,
            outline: "none",
            width: "100%",
            minHeight: 44,
            lineHeight: 1.4,
            color: "#333",
          }}
        />
      ) : (
        <div
          className="nodrag"
          style={{
            fontFamily: "Helvetica, Arial, sans-serif",
            fontSize: 12,
            lineHeight: 1.4,
            color: d.text ? "#333" : "#aaa",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            minWidth: 100,
            minHeight: 44,
          }}
        >
          {d.text || "Double-click to add note…"}
        </div>
      )}
    </div>
  );
}

export const nodeTypes = {
  start: StartNode,
  decision: DecisionNode,
  process: ProcessNode,
  action: ActionNode,
  end: EndNode,
  annotation: AnnotationNode,
};
