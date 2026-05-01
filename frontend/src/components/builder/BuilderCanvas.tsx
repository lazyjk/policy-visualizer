/**
 * BuilderCanvas — React Flow canvas for assembling a ClearPass service.
 *
 * 4 pre-wired nodes in a linear chain:
 *   ServiceMatch → Auth → RoleMapping → Enforcement
 *
 * Nodes are clickable to open BuilderSidePanel.
 * Drag from ElementsLibrary onto canvas to populate policy nodes.
 */
import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { CanvasState, ClearPassCredentials } from "../../api/builderApi";
import ServiceMatchNode from "./nodes/ServiceMatchNode";
import AuthNode from "./nodes/AuthNode";
import RoleMappingNode from "./nodes/RoleMappingNode";
import EnforcementPolicyNode from "./nodes/EnforcementPolicyNode";

export type SelectedNodeType = "service" | "auth" | "roleMapping" | "enforcement" | null;

const NODE_TYPES = {
  serviceMatch: ServiceMatchNode,
  auth: AuthNode,
  roleMapping: RoleMappingNode,
  enforcement: EnforcementPolicyNode,
};

const EDGE_STYLE = { stroke: "#94a3b8", strokeWidth: 2 };

interface Props {
  canvasState: CanvasState | null;
  selectedNode?: SelectedNodeType;
  onNodeSelect: (node: SelectedNodeType) => void;
  onNewService: () => void;
  onPreview: () => void;
  onExport: () => void;
  onDrop?: (sectionKey: string, item: Record<string, unknown>) => void;
  creds: ClearPassCredentials | null;
}

export default function BuilderCanvas({
  canvasState,
  onNodeSelect,
  onNewService,
  onPreview,
  onExport,
  onDrop,
}: Props) {
  const nodes: Node[] = useMemo(() => {
    if (!canvasState) return [];
    return [
      {
        id: "service",
        type: "serviceMatch",
        position: { x: 40, y: 120 },
        data: { service: canvasState.service },
        selectable: true,
        draggable: false,
      },
      {
        id: "auth",
        type: "auth",
        position: { x: 300, y: 120 },
        data: { auth: canvasState.auth },
        selectable: true,
        draggable: false,
      },
      {
        id: "roleMapping",
        type: "roleMapping",
        position: { x: 560, y: 120 },
        data: { roleMapping: canvasState.roleMappingPolicy },
        selectable: true,
        draggable: false,
      },
      {
        id: "enforcement",
        type: "enforcement",
        position: { x: 820, y: 120 },
        data: { enforcement: canvasState.enforcementPolicy },
        selectable: true,
        draggable: false,
      },
    ];
  }, [canvasState]);

  const edges: Edge[] = useMemo(() => {
    if (!canvasState) return [];
    return [
      { id: "e-service-auth", source: "service", target: "auth", style: EDGE_STYLE, animated: false },
      { id: "e-auth-rm", source: "auth", target: "roleMapping", style: EDGE_STYLE, animated: false },
      { id: "e-rm-enf", source: "roleMapping", target: "enforcement", style: EDGE_STYLE, animated: false },
    ];
  }, [canvasState]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      const idMap: Record<string, SelectedNodeType> = {
        service: "service",
        auth: "auth",
        roleMapping: "roleMapping",
        enforcement: "enforcement",
      };
      onNodeSelect(idMap[node.id] ?? null);
    },
    [onNodeSelect]
  );

  const handlePaneClick = useCallback(() => {
    onNodeSelect(null);
  }, [onNodeSelect]);

  // DragOver / Drop from ElementsLibrary
  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const raw = e.dataTransfer.getData("application/builder-item");
    if (!raw || !onDrop) return;
    try {
      const { sectionKey, item } = JSON.parse(raw) as { sectionKey: string; item: Record<string, unknown> };
      onDrop(sectionKey, item);
    } catch {
      // ignore malformed drag data
    }
  }

  const hasCanvas = canvasState !== null;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", position: "relative" }}>
      {/* Toolbar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 12px",
        borderBottom: "1px solid #e5e7eb",
        background: "#fff",
        flexShrink: 0,
      }}>
        <button
          onClick={onNewService}
          style={{
            padding: "6px 14px",
            background: "#3b82f6",
            color: "#fff",
            border: "none",
            borderRadius: 5,
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: "Helvetica, Arial, sans-serif",
          }}
        >
          + New Service
        </button>

        {hasCanvas && (
          <>
            <div style={{ width: 1, height: 20, background: "#e5e7eb", margin: "0 4px" }} />
            <button
              onClick={onPreview}
              style={{
                padding: "6px 14px",
                background: "#fff",
                color: "#374151",
                border: "1px solid #d1d5db",
                borderRadius: 5,
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
                fontFamily: "Helvetica, Arial, sans-serif",
              }}
            >
              Preview
            </button>
            <button
              onClick={onExport}
              style={{
                padding: "6px 14px",
                background: "#fff",
                color: "#374151",
                border: "1px solid #d1d5db",
                borderRadius: 5,
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
                fontFamily: "Helvetica, Arial, sans-serif",
              }}
            >
              Export JSON
            </button>
          </>
        )}
      </div>

      {/* Canvas area */}
      <div style={{ flex: 1, position: "relative" }} onDragOver={handleDragOver} onDrop={handleDrop}>
        {!hasCanvas ? (
          <div style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            color: "#9ca3af",
            fontFamily: "Helvetica, Arial, sans-serif",
            pointerEvents: "none",
          }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>⊕</div>
            <div style={{ fontSize: 15, marginBottom: 4 }}>Click <strong style={{ color: "#374151" }}>+ New Service</strong> to start building</div>
            <div style={{ fontSize: 13 }}>or connect a ClearPass instance to browse existing elements</div>
          </div>
        ) : null}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodeClick={handleNodeClick}
          onPaneClick={handlePaneClick}
          nodesConnectable={false}
          edgesReconnectable={false}
          nodesDraggable={false}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          style={{ background: "#f9fafb" }}
        >
          <Background color="#e5e7eb" gap={20} size={1} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}
