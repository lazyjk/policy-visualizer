/**
 * Custom React Flow node types.
 * Colors match the existing Graphviz renderer in src/renderer.py.
 */
import React from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

interface NodeData {
  label: string;
  sub_label?: string;
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
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: "#AED6F1",
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
export function DecisionNode({ data }: NodeProps) {
  const d = data as NodeData;
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        position: "relative",
        width: 220,
        height: 220,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Handle type="target" position={Position.Left} />
      <Handle type="target" position={Position.Top} id="top" />
      <div
        style={{
          background: "#FAD7A0",
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
          {multilineLabel(d.label)}
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
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: "#A9DFBF",
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
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: "#D7BDE2",
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
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: "#F1948A",
        border: "4px double #E74C3C",
        borderRadius: "50%",
        padding: "10px 14px",
      }}
    >
      <Handle type="target" position={Position.Left} />
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

export const nodeTypes = {
  start: StartNode,
  decision: DecisionNode,
  process: ProcessNode,
  action: ActionNode,
  end: EndNode,
};
