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
  const [flow, setFlow] = useState<FlowIR | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFileSelect(file: File) {
    fileRef.current = file;
    setFlow(null);
    setServices([]);
    setError(null);
    setLoading(true);
    try {
      const result = await fetchServices(file);
      if (result.services.length === 1) {
        // Only one service — skip the picker and render immediately
        await loadFlow(file, result.services[0].name);
      } else {
        setServices(result.services);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadFlow(file: File, serviceName: string) {
    setError(null);
    setLoading(true);
    try {
      const flowData = await fetchFlow(file, serviceName);
      setFlow(flowData);
      setServices([]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleServiceSelect(name: string) {
    if (!fileRef.current) return;
    await loadFlow(fileRef.current, name);
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <UploadPanel
        services={services}
        loading={loading}
        error={error}
        onFileSelect={handleFileSelect}
        onServiceSelect={handleServiceSelect}
      />
      <div style={{ flex: 1, position: "relative", background: "#f9fafb" }}>
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
            {loading ? "Compiling diagram…" : "Upload a ClearPass XML file to begin"}
          </div>
        )}
      </div>
    </div>
  );
}
