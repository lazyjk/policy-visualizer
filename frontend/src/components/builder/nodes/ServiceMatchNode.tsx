import { Handle, Position } from "@xyflow/react";
import type { CanvasServiceState } from "../../../api/builderApi";

interface ServiceMatchNodeData {
  service: CanvasServiceState;
  selected?: boolean;
}

export default function ServiceMatchNode({ data }: { data: ServiceMatchNodeData }) {
  const { service } = data;
  const condCount = service.match?.conditions.length ?? 0;

  return (
    <div
      style={{
        background: "#eff6ff",
        border: "2px solid #3b82f6",
        borderRadius: 8,
        padding: "10px 14px",
        minWidth: 180,
        maxWidth: 240,
        height: 90,
        boxSizing: "border-box",
        fontFamily: "Helvetica, Arial, sans-serif",
        cursor: "pointer",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{
          fontSize: 10,
          fontWeight: 700,
          background: service.serviceType === "TACACS" ? "#ede9fe" : "#dbeafe",
          color: service.serviceType === "TACACS" ? "#7c3aed" : "#1d4ed8",
          borderRadius: 4,
          padding: "1px 6px",
        }}>
          {service.serviceType}
        </span>
        <span style={{ fontSize: 10, color: "#6b7280", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
          Service
        </span>
      </div>
      <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {service.name || <em style={{ color: "#9ca3af" }}>Unnamed service</em>}
      </div>
      <div style={{ fontSize: 11, color: "#6b7280" }}>
        {condCount === 0
          ? "No match conditions"
          : `${condCount} match condition${condCount !== 1 ? "s" : ""}`}
      </div>

      <Handle type="source" position={Position.Right} id="right" style={{ background: "#3b82f6" }} />
    </div>
  );
}
