import { Handle, Position } from "@xyflow/react";
import type { CanvasEnforcementState } from "../../../api/builderApi";

interface EnforcementPolicyNodeData {
  enforcement: CanvasEnforcementState;
}

export default function EnforcementPolicyNode({ data }: { data: EnforcementPolicyNodeData }) {
  const { enforcement } = data;
  const ruleCount = enforcement.rules.length;

  return (
    <div
      style={{
        background: "#fdf4ff",
        border: "2px solid #a855f7",
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
        Enforcement
      </div>
      <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {enforcement.name || <em style={{ color: "#9ca3af" }}>New Enforcement Policy</em>}
      </div>
      <div style={{ fontSize: 11, color: "#6b7280", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {ruleCount === 0 ? "No rules" : `${ruleCount} rule${ruleCount !== 1 ? "s" : ""}`}
        {enforcement.defaultProfileNames.length > 0
          ? ` · default: ${enforcement.defaultProfileNames.join(", ")}`
          : ""}
      </div>

      <Handle type="target" position={Position.Left} id="left" style={{ background: "#a855f7" }} />
    </div>
  );
}
