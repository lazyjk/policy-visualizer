/**
 * PreviewModal — renders the assembled service as a flow diagram.
 *
 * Calls POST /api/flow/from-ir with the canvas state, then renders the
 * returned FlowIR inside the existing FlowDiagram component.
 */
import { useEffect, useState } from "react";
import type { CanvasState } from "../../api/builderApi";
import { previewFromIR } from "../../api/builderApi";
import type { FlowIR } from "../../api";
import FlowDiagram from "../FlowDiagram";

interface Props {
  canvasState: CanvasState;
  onClose: () => void;
}

export default function PreviewModal({ canvasState, onClose }: Props) {
  const [flowIR, setFlowIR] = useState<FlowIR | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    previewFromIR(canvasState)
      .then((ir) => setFlowIR(ir))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.55)",
      display: "flex",
      flexDirection: "column",
      zIndex: 1200,
    }}>
      {/* Modal chrome */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "12px 20px",
        background: "#1e293b",
        color: "#fff",
        flexShrink: 0,
      }}>
        <span style={{ fontFamily: "Helvetica, Arial, sans-serif", fontSize: 15, fontWeight: 600 }}>
          Preview — {canvasState.service.name}
        </span>
        <button
          onClick={onClose}
          style={{
            padding: "6px 16px",
            background: "rgba(255,255,255,0.15)",
            color: "#fff",
            border: "1px solid rgba(255,255,255,0.25)",
            borderRadius: 5,
            fontSize: 13,
            cursor: "pointer",
            fontFamily: "Helvetica, Arial, sans-serif",
          }}
        >
          Close
        </button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, position: "relative", background: "#f9fafb" }}>
        {loading && (
          <div style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#6b7280",
            fontFamily: "Helvetica, Arial, sans-serif",
            fontSize: 14,
          }}>
            Compiling flow diagram…
          </div>
        )}
        {error && (
          <div style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexDirection: "column",
            gap: 12,
            fontFamily: "Helvetica, Arial, sans-serif",
          }}>
            <div style={{ color: "#dc2626", fontSize: 14 }}>Failed to compile preview</div>
            <div style={{ color: "#9ca3af", fontSize: 12, maxWidth: 400, textAlign: "center" }}>{error}</div>
            <button onClick={onClose} style={{
              padding: "8px 20px",
              background: "#f3f4f6",
              border: "none",
              borderRadius: 5,
              fontSize: 13,
              cursor: "pointer",
              fontFamily: "Helvetica, Arial, sans-serif",
            }}>
              Close
            </button>
          </div>
        )}
        {!loading && !error && flowIR && (
          <FlowDiagram flow={flowIR} />
        )}
      </div>
    </div>
  );
}
