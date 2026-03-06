import { createContext, useContext, useReducer, type Dispatch, type ReactNode } from "react";
import type { Node, Edge } from "@xyflow/react";
import type { NodeColors } from "../components/nodes/nodeTypes";
import { DEFAULT_NODE_COLORS } from "../components/nodes/nodeTypes";

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

export interface DiagramEditState {
  annotationNodes: Node[];
  annotationEdges: Edge[];
  nodeColors: NodeColors;
  // viewport reserved for future restore; not yet wired
}

export interface AnnotationClipboard {
  nodes: Node[];   // deep-cloned annotation nodes with remapped IDs
  edges: Edge[];   // annotation edges between copied nodes with remapped IDs
  sourceServiceId: string;
}

interface DiagramSessionState {
  editStates: Record<string, DiagramEditState>;
  clipboard: AnnotationClipboard | null;
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

export type DiagramSessionAction =
  | { type: "SAVE_EDIT_STATE"; serviceId: string; state: DiagramEditState }
  | { type: "SET_CLIPBOARD"; payload: AnnotationClipboard }
  | { type: "CLEAR_SESSION" };

const initialState: DiagramSessionState = {
  editStates: {},
  clipboard: null,
};

function reducer(state: DiagramSessionState, action: DiagramSessionAction): DiagramSessionState {
  switch (action.type) {
    case "SAVE_EDIT_STATE":
      return {
        ...state,
        editStates: { ...state.editStates, [action.serviceId]: action.state },
      };
    case "SET_CLIPBOARD":
      return { ...state, clipboard: action.payload };
    case "CLEAR_SESSION":
      return initialState;
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface DiagramSessionContextValue {
  state: DiagramSessionState;
  dispatch: Dispatch<DiagramSessionAction>;
}

const DiagramSessionContext = createContext<DiagramSessionContextValue | null>(null);

export function DiagramSessionProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <DiagramSessionContext.Provider value={{ state, dispatch }}>
      {children}
    </DiagramSessionContext.Provider>
  );
}

export function useDiagramSession() {
  const ctx = useContext(DiagramSessionContext);
  if (!ctx) throw new Error("useDiagramSession must be used within DiagramSessionProvider");
  return ctx;
}

// Re-export default colors so callers don't need a separate import
export { DEFAULT_NODE_COLORS };
