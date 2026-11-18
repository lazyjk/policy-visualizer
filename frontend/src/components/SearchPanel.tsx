/**
 * SearchPanel — find nodes in the current diagram.
 *
 * Matches (case-insensitive substring) against each diagram node's label and
 * sub_label, plus the linked rule detail (condition, action, profile names and
 * attribute values) so role names / VLANs shown only in the inspector are
 * findable too. Results follow flow.nodes order (deterministic).
 *
 * Highlighting is applied as React Flow node classNames:
 *   search-match   every hit
 *   search-current the active hit
 *   search-dim     every non-hit diagram node
 * Styles live in index.css and are neutralised under .pv-exporting so image
 * exports never include search styling.
 *
 * Must be rendered inside <ReactFlow> (uses useReactFlow / useStore).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Panel, useReactFlow, useStore } from "@xyflow/react";
import type { FlowIR, FlowNode, PolicyDetails } from "../api";

interface Props {
  flow: FlowIR;
  details?: PolicyDetails;
  onNodeSelect?: (node: FlowNode | null) => void;
}

const SEARCH_CLASSES = ["search-match", "search-current", "search-dim"];

function searchableText(node: FlowNode, details?: PolicyDetails): string {
  const parts: string[] = [node.label, node.sub_label];
  const rule = node.trace_rule_id ? details?.rule_index[node.trace_rule_id] : undefined;
  // Only action/decision nodes carry rule content; avoid making both the
  // decision and its action match on profile attributes — attributes belong
  // to the action node.
  if (rule) {
    if (node.type === "decision") {
      parts.push(rule.condition_text);
    } else {
      parts.push(rule.action_text);
      for (const p of rule.profiles ?? []) {
        parts.push(p.name);
        for (const a of p.attributes) parts.push(a.name, a.display_value || a.value);
      }
    }
  }
  return parts.join("\n").toLowerCase();
}

function stripSearchClasses(className: string | undefined): string {
  return (className ?? "")
    .split(/\s+/)
    .filter((c) => c && !SEARCH_CLASSES.includes(c))
    .join(" ");
}

export default function SearchPanel({ flow, details, onNodeSelect }: Props) {
  const { setNodes, fitView } = useReactFlow();
  const [query, setQuery] = useState("");
  const [current, setCurrent] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Pre-compute lowercase search text per diagram node.
  const index = useMemo(
    () => flow.nodes.map((n) => ({ node: n, text: searchableText(n, details) })),
    [flow.nodes, details],
  );

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [] as FlowNode[];
    return index.filter((e) => e.text.includes(q)).map((e) => e.node);
  }, [index, query]);

  const active = query.trim() !== "";
  const safeCurrent = matches.length ? Math.min(current, matches.length - 1) : 0;
  const currentNode = matches[safeCurrent] ?? null;

  // Re-apply classes whenever the node set changes (layout, batch-export
  // restore, color changes). The diff guard prevents an update loop.
  const storeNodes = useStore((s) => s.nodes);
  useEffect(() => {
    const matchIds = new Set(matches.map((m) => m.id));
    const diagramIds = new Set(flow.nodes.map((n) => n.id));
    const desired = (id: string, existing: string | undefined): string | undefined => {
      const base = stripSearchClasses(existing);
      if (!active || !diagramIds.has(id)) return base || undefined;
      const extra = matchIds.has(id)
        ? id === currentNode?.id ? "search-match search-current" : "search-match"
        : "search-dim";
      return [base, extra].filter(Boolean).join(" ");
    };
    const needsUpdate = storeNodes.some((n) => (n.className || undefined) !== desired(n.id, n.className));
    if (!needsUpdate) return;
    setNodes((nds) => nds.map((n) => {
      const cls = desired(n.id, n.className);
      return (n.className || undefined) === cls ? n : { ...n, className: cls };
    }));
  }, [storeNodes, matches, currentNode, active, flow.nodes, setNodes]);

  // Clear highlight classes when the panel unmounts (e.g. service switch).
  useEffect(() => () => {
    setNodes((nds) => nds.map((n) =>
      n.className && SEARCH_CLASSES.some((c) => n.className!.includes(c))
        ? { ...n, className: stripSearchClasses(n.className) || undefined }
        : n,
    ));
  }, [setNodes]);

  // Pan to and select the current hit.
  useEffect(() => {
    if (!currentNode) return;
    fitView({ nodes: [{ id: currentNode.id }], duration: 300, maxZoom: 1.2, padding: 0.4 });
    onNodeSelect?.(currentNode);
  }, [currentNode, fitView, onNodeSelect]);

  function step(delta: number) {
    if (!matches.length) return;
    setCurrent((c) => (Math.min(c, matches.length - 1) + delta + matches.length) % matches.length);
  }

  function clear() {
    setQuery("");
    setCurrent(0);
    inputRef.current?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      step(e.shiftKey ? -1 : 1);
    } else if (e.key === "Escape") {
      e.preventDefault();
      clear();
    }
  }

  return (
    <Panel position="top-center" className="nokey" style={{ marginTop: 44 }}>
      <div style={wrapStyle}>
        <span aria-hidden="true" style={{ color: "#9ca3af", fontSize: 13 }}>⌕</span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setCurrent(0); }}
          onKeyDown={onKeyDown}
          placeholder="Search nodes, roles, VLANs…"
          aria-label="Search diagram nodes"
          style={inputStyle}
        />
        {active && (
          <span style={counterStyle} aria-live="polite">
            {matches.length ? `${safeCurrent + 1} of ${matches.length}` : "No matches"}
          </span>
        )}
        <button style={iconButtonStyle} onClick={() => step(-1)} disabled={!matches.length}
          title="Previous match (Shift+Enter)" aria-label="Previous match">‹</button>
        <button style={iconButtonStyle} onClick={() => step(1)} disabled={!matches.length}
          title="Next match (Enter)" aria-label="Next match">›</button>
        {active && (
          <button style={iconButtonStyle} onClick={clear} title="Clear search (Esc)" aria-label="Clear search">✕</button>
        )}
      </div>
    </Panel>
  );
}

const wrapStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 4,
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  padding: "4px 6px",
  boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
  fontFamily: "Helvetica, Arial, sans-serif",
};

const inputStyle: React.CSSProperties = {
  width: 210,
  fontSize: 12,
  padding: "4px 6px",
  border: "none",
  outline: "none",
  background: "transparent",
  color: "#111827",
  fontFamily: "inherit",
};

const counterStyle: React.CSSProperties = {
  fontSize: 11,
  color: "#6b7280",
  whiteSpace: "nowrap",
  padding: "0 4px",
};

const iconButtonStyle: React.CSSProperties = {
  width: 24,
  height: 24,
  border: "1px solid #e5e7eb",
  borderRadius: 5,
  background: "#f9fafb",
  color: "#374151",
  fontSize: 13,
  lineHeight: 1,
  padding: 0,
};
