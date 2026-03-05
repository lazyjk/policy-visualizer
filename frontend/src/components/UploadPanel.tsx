/**
 * UploadPanel — XML file upload and optional service picker.
 */
import { useRef, useState } from "react";
import type { ServiceSummary } from "../api";

interface Props {
  services: ServiceSummary[];
  selectedService: string | null;
  fileName: string | null;
  loading: boolean;
  error: string | null;
  onFileSelect: (file: File) => void;
  onServiceSelect: (id: string) => void;
}

export default function UploadPanel({
  services,
  selectedService,
  fileName,
  loading,
  error,
  onFileSelect,
  onServiceSelect,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleFile(file: File) {
    if (!file.name.endsWith(".xml")) {
      alert("Please upload an XML file (.xml).");
      return;
    }
    onFileSelect(file);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  return (
    <div style={panelStyle}>
      <h2 style={{ margin: "0 0 16px", fontSize: 16, fontWeight: 600 }}>
        Policy Visualizer
      </h2>

      {/* Drop zone */}
      <div
        style={{
          ...dropZoneStyle,
          borderColor: dragging ? "#6366f1" : "#d1d5db",
          background: dragging ? "#eef2ff" : "#f9fafb",
        }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".xml"
          style={{ display: "none" }}
          onChange={handleChange}
        />
        <span style={{ fontSize: 28 }}>📁</span>
        <p style={{ margin: "8px 0 0", fontSize: 13, color: "#6b7280" }}>
          {loading ? "Processing…" : "Drop a service or policy XML file here or click to browse"}
        </p>
      </div>

      {/* Current file */}
      {fileName && (
        <div style={fileNameStyle}>
          <span style={{ marginRight: 6 }}>📄</span>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {fileName}
          </span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={errorStyle}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Service picker */}
      {services.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <p style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 500 }}>
            Select a service to visualize:
          </p>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {services.map((svc) => {
              const isActive = svc.id === selectedService;
              return (
                <li key={svc.id} style={{ marginBottom: 6 }}>
                  <button
                    style={isActive ? activeServiceButtonStyle : serviceButtonStyle}
                    onClick={() => onServiceSelect(svc.id)}
                    title={svc.description || undefined}
                  >
                    <span>{svc.name}</span>
                    <span style={serviceTypeBadgeStyle}>{svc.service_type}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

const panelStyle: React.CSSProperties = {
  width: 280,
  minWidth: 280,
  background: "#fff",
  borderRight: "1px solid #e5e7eb",
  padding: "20px 16px",
  overflowY: "auto",
  fontFamily: "Helvetica, Arial, sans-serif",
};

const dropZoneStyle: React.CSSProperties = {
  border: "2px dashed",
  borderRadius: 8,
  padding: "24px 16px",
  textAlign: "center",
  cursor: "pointer",
  transition: "border-color 0.15s, background 0.15s",
};

const fileNameStyle: React.CSSProperties = {
  marginTop: 12,
  padding: "8px 10px",
  background: "#f0fdf4",
  border: "1px solid #bbf7d0",
  borderRadius: 6,
  fontSize: 12,
  color: "#15803d",
  display: "flex",
  alignItems: "center",
};

const errorStyle: React.CSSProperties = {
  marginTop: 12,
  padding: "10px 12px",
  background: "#fef2f2",
  border: "1px solid #fca5a5",
  borderRadius: 6,
  fontSize: 12,
  color: "#dc2626",
};

const serviceButtonStyle: React.CSSProperties = {
  width: "100%",
  textAlign: "left",
  padding: "8px 10px",
  background: "#f3f4f6",
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 12,
  fontFamily: "inherit",
  color: "#111827",
};

const activeServiceButtonStyle: React.CSSProperties = {
  ...serviceButtonStyle,
  background: "#eef2ff",
  border: "1px solid #6366f1",
  color: "#4338ca",
  fontWeight: 600,
};

const serviceTypeBadgeStyle: React.CSSProperties = {
  marginLeft: 6,
  fontSize: 10,
  fontWeight: 600,
  color: "#6b7280",
  background: "#e5e7eb",
  borderRadius: 4,
  padding: "1px 5px",
  verticalAlign: "middle",
};
