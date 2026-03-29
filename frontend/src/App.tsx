import { useState, useRef } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import UploadPanel from "./components/UploadPanel";
import FlowDiagram from "./components/FlowDiagram";
import { fetchServices, fetchFlow } from "./api";
import type { FlowIR, FlowNode, ServiceSummary } from "./api";
import PolicyDetailsPanel from "./components/PolicyDetailsPanel";
import BuilderView from "./components/builder/BuilderView";
import { DiagramSessionProvider, useDiagramSession } from "./context/DiagramSessionContext";
import { version } from "../package.json";
import "./App.css";

type ActiveTab = "visualize" | "build";

export default function App() {
  return (
    <DiagramSessionProvider>
      <AppContent />
    </DiagramSessionProvider>
  );
}

function AppContent() {
  const { dispatch: sessionDispatch } = useDiagramSession();
  const [activeTab, setActiveTab] = useState<ActiveTab>("visualize");
  const fileRef = useRef<File | null>(null);
  const [services, setServices] = useState<ServiceSummary[]>([]);
  const [selectedService, setSelectedService] = useState<string | null>(null);
  const [flow, setFlow] = useState<FlowIR | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [dismissedWarnings, setDismissedWarnings] = useState(false);
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null);

  async function handleFileSelect(file: File) {
    sessionDispatch({ type: "CLEAR_SESSION" });
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
    setSelectedNode(null);
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
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
      {/* Tab bar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        borderBottom: "1px solid #e5e7eb",
        background: "#fff",
        padding: "0 16px",
        height: 44,
        flexShrink: 0,
        gap: 4,
      }}>
        <span style={{ fontWeight: 700, fontSize: 14, color: "#111827", marginRight: 16, fontFamily: "Helvetica, Arial, sans-serif" }}>
          Policy Visualizer
        </span>
        {(["visualize", "build"] as ActiveTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "6px 14px",
              border: "none",
              borderBottom: activeTab === tab ? "2px solid #2563eb" : "2px solid transparent",
              background: "none",
              fontFamily: "Helvetica, Arial, sans-serif",
              fontSize: 13,
              fontWeight: activeTab === tab ? 600 : 400,
              color: activeTab === tab ? "#2563eb" : "#6b7280",
              cursor: "pointer",
              marginBottom: -1,
            }}
          >
            {tab === "visualize" ? "Visualize" : "Build"}
          </button>
        ))}
      </div>

      {/* Content — both tabs stay mounted to preserve state across switches */}
      <div style={{ display: activeTab === "build" ? "flex" : "none", flex: 1, overflow: "hidden" }}>
        <BuilderView />
      </div>
      <div style={{ display: activeTab === "visualize" ? "flex" : "none", flex: 1, overflow: "hidden" }}>
          <UploadPanel
            services={services}
            selectedService={selectedService}
            fileName={fileName}
            loading={loading}
            error={error}
            onFileSelect={handleFileSelect}
            onServiceSelect={handleServiceSelect}
          />
          <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
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
                  <FlowDiagram
                    flow={flow}
                    allServices={services}
                    fileRef={fileRef}
                    onNodeSelect={setSelectedNode}
                  />
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
            {flow && (
              <PolicyDetailsPanel details={flow.details} selectedNode={selectedNode} />
            )}
          </div>
        </div>

      {/* Version watermark */}
      <div style={{
        position: "fixed", bottom: 10, left: 10, zIndex: 100,
        fontFamily: "Helvetica, Arial, sans-serif", fontSize: 11,
        color: "#9ca3af", pointerEvents: "none", userSelect: "none",
      }}>
        v{version}
      </div>
    </div>
  );
}
