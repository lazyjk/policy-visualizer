import { Handle, Position } from "@xyflow/react";
import type { CanvasAuthState } from "../../../api/builderApi";

interface AuthNodeData {
  auth: CanvasAuthState;
}

export default function AuthNode({ data }: { data: AuthNodeData }) {
  const { auth } = data;
  const methodNames = auth.methods.map((m) => m.name).join(", ") || "None";
  const sourceNames = auth.sources.map((s) => s.name).join(", ") || "None";

  return (
    <div
      style={{
        background: "#f0fdf4",
        border: "2px solid #22c55e",
        borderRadius: 8,
        padding: "10px 14px",
        minWidth: 190,
        maxWidth: 240,
        height: 90,
        boxSizing: "border-box",
        fontFamily: "Helvetica, Arial, sans-serif",
        cursor: "pointer",
      }}
    >
      <div style={{ fontSize: 10, color: "#6b7280", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
        Authentication
      </div>
      <div style={{ marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: "#6b7280" }}>Methods: </span>
        <span
          style={{
            fontSize: 12,
            color: "#111827",
            fontWeight: 500,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            display: "inline-block",
            maxWidth: 130,
            verticalAlign: "bottom",
          }}
          title={methodNames}
        >
          {methodNames}
        </span>
      </div>
      <div>
        <span style={{ fontSize: 11, color: "#6b7280" }}>Sources: </span>
        <span
          style={{
            fontSize: 12,
            color: "#111827",
            fontWeight: 500,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            display: "inline-block",
            maxWidth: 130,
            verticalAlign: "bottom",
          }}
          title={sourceNames}
        >
          {sourceNames}
        </span>
      </div>

      <Handle type="target" position={Position.Left} id="left" style={{ background: "#22c55e" }} />
      <Handle type="source" position={Position.Right} id="right" style={{ background: "#22c55e" }} />
    </div>
  );
}
