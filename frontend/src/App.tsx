import { useState, useRef } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import UploadPanel from "./components/UploadPanel";
import FlowDiagram from "./components/FlowDiagram";
import { fetchServices, fetchFlow } from "./api";
import type { FlowIR, ServiceSummary } from "./api";
import "./App.css";

export default function App() {
  const fileRef = useRef<File | null>(null);
  const [services, setServices] = useState<ServiceSummary[]>([]);
  const [selectedService, setSelectedService] = useState<string | null>(null);
  const [flow, setFlow] = useState<FlowIR | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [dismissedWarnings, setDismissedWarnings] = useState(false);

  async function handleFileSelect(file: File) {
    fileRef.current = file;
    setFileName(file.name);
    setFlow(null);
    setServices([]);
    setSelectedService(null);
    setError(null);
    setLoading(true);
    try {
      const result = await fetchServices(file);
      setServices(result.services);
      if (result.services.length === 1) {
        // Only one service — render immediately
        await loadFlow(file, result.services[0].id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadFlow(file: File, serviceId: string) {
    setError(null);
    setDismissedWarnings(false);
    setLoading(true);
    try {
      const flowData = await fetchFlow(file, serviceId);
      setFlow(flowData);
      setSelectedService(serviceId);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleServiceSelect(id: string) {
    if (!fileRef.current) return;
    await loadFlow(fileRef.current, id);
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <UploadPanel
        services={services}
        selectedService={selectedService}
        fileName={fileName}
        loading={loading}
        error={error}
        onFileSelect={handleFileSelect}
        onServiceSelect={handleServiceSelect}
      />
      <div style={{ flex: 1, position: "relative", background: "#f9fafb" }}>
        {flow && flow.warnings.length > 0 && !dismissedWarnings && (
          <div style={{
            position: "absolute", top: 0, left: 0, right: 0, zIndex: 10,
            background: "#fef3c7", borderBottom: "1px solid #f59e0b",
            padding: "8px 16px", fontFamily: "Helvetica, Arial, sans-serif",
            fontSize: 13, color: "#92400e", display: "flex",
            justifyContent: "space-between", alignItems: "flex-start",
          }}>
            <div>
              <strong>Partial result</strong> — some references could not be resolved:
              <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
                {flow.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
            <button
              onClick={() => setDismissedWarnings(true)}
              style={{ marginLeft: 16, background: "none", border: "none",
                       cursor: "pointer", fontSize: 16, color: "#92400e" }}
            >
              ✕
            </button>
          </div>
        )}
        {flow ? (
          <ReactFlowProvider>
            <FlowDiagram flow={flow} />
          </ReactFlowProvider>
        ) : (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              color: "#9ca3af",
              fontFamily: "Helvetica, Arial, sans-serif",
              fontSize: 15,
            }}
          >
            {loading ? "Compiling diagram…" : "Upload a service or policy XML file to begin"}
          </div>
        )}
      </div>
    </div>
  );
}
