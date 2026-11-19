/**
 * CoverageModal — preview and download the anonymous coverage report.
 *
 * The report holds counts only (service templates, profile types, condition
 * namespaces/operators, uninterpreted setting shapes): no names, descriptions
 * or values. Users review it here before saving and sharing it.
 */
import { useEffect } from "react";
import type { CoverageReport } from "../api";

interface Props {
  report: CoverageReport;
  fileName: string | null;
  onClose: () => void;
}

export default function CoverageModal({ report, fileName, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const json = JSON.stringify(report, null, 2);

  function download() {
    const blob = new Blob([json + "\n"], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "policy-visualizer-coverage.json";  // never the uploaded file's name
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div style={overlayStyle} onClick={onClose} role="presentation">
      <div style={dialogStyle} onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Coverage report">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#111827" }}>Coverage report</div>
            {fileName && <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>{fileName}</div>}
          </div>
          <button onClick={onClose} style={closeStyle} aria-label="Close">✕</button>
        </div>
        <div style={noticeStyle}>
          Counts of the features this configuration uses, to help prioritise support. It contains
          no names, descriptions or values. Review it below before sharing.
        </div>
        <pre style={preStyle}>{json}</pre>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} style={secondaryButtonStyle}>Close</button>
          <button onClick={download} style={primaryButtonStyle}>Download JSON</button>
        </div>
      </div>
    </div>
  );
}

const overlayStyle: React.CSSProperties = {
  position: "fixed", inset: 0, zIndex: 1000, background: "rgba(17, 24, 39, 0.35)",
  display: "flex", alignItems: "center", justifyContent: "center",
  fontFamily: "Helvetica, Arial, sans-serif",
};

const dialogStyle: React.CSSProperties = {
  width: "min(640px, calc(100vw - 32px))", maxHeight: "calc(100vh - 64px)",
  display: "flex", flexDirection: "column", gap: 12,
  background: "#fff", borderRadius: 10, padding: "18px 20px",
  boxShadow: "0 20px 40px rgba(0,0,0,0.18)",
};

const closeStyle: React.CSSProperties = {
  background: "none", border: "none", cursor: "pointer", fontSize: 16, color: "#6b7280", padding: 4,
};

const noticeStyle: React.CSSProperties = {
  padding: "8px 10px", background: "#eff6ff", border: "1px solid #bfdbfe",
  borderRadius: 6, fontSize: 12, color: "#1e3a8a",
};

const preStyle: React.CSSProperties = {
  flex: 1, minHeight: 0, overflow: "auto", margin: 0, padding: 10,
  background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6,
  fontSize: 11, lineHeight: 1.45, color: "#111827",
};

const secondaryButtonStyle: React.CSSProperties = {
  padding: "6px 12px", fontSize: 12, fontFamily: "inherit", cursor: "pointer",
  background: "#fff", border: "1px solid #d1d5db", borderRadius: 6, color: "#374151",
};

const primaryButtonStyle: React.CSSProperties = {
  ...secondaryButtonStyle, background: "#4338ca", border: "1px solid #4338ca", color: "#fff",
};
