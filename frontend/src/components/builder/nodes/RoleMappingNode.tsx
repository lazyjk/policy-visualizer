import { Handle, Position } from "@xyflow/react";
import type { CanvasRoleMappingState } from "../../../api/builderApi";

interface RoleMappingNodeData {
  roleMapping: CanvasRoleMappingState;
}

export default function RoleMappingNode({ data }: { data: RoleMappingNodeData }) {
  const { roleMapping } = data;
  const ruleCount = roleMapping.rules.length;

  return (
    <div
      style={{
        background: "#fffbeb",
        border: "2px solid #f59e0b",
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
      <div style={{ fontSize: 10, color: "#6b7280", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
        Role Mapping
      </div>
      <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {roleMapping.name || <em style={{ color: "#9ca3af" }}>New Role Mapping Policy</em>}
      </div>
      <div style={{ fontSize: 11, color: "#6b7280", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {ruleCount === 0 ? "No rules" : `${ruleCount} rule${ruleCount !== 1 ? "s" : ""}`}
        {roleMapping.defaultRoleName ? ` · default: ${roleMapping.defaultRoleName}` : ""}
      </div>

      <Handle type="target" position={Position.Left} id="left" style={{ background: "#f59e0b" }} />
      <Handle type="source" position={Position.Right} id="right" style={{ background: "#f59e0b" }} />
    </div>
  );
}
