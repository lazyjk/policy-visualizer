import type { FlowNode, PolicyDetails, RuleDetail } from "../api";

interface PolicyDetailsPanelProps {
  details: PolicyDetails | undefined;
  selectedNode: FlowNode | null;
}

const PANEL_STYLE: React.CSSProperties = {
  width: 320,
  minWidth: 320,
  maxWidth: 320,
  height: "100%",
  overflowY: "auto",
  borderLeft: "1px solid #e5e7eb",
  backgroundColor: "#ffffff",
  fontFamily: "Helvetica, Arial, sans-serif",
  fontSize: 13,
  display: "flex",
  flexDirection: "column",
};

const HEADER_STYLE: React.CSSProperties = {
  padding: "12px 14px 10px",
  borderBottom: "1px solid #e5e7eb",
  fontWeight: 600,
  fontSize: 13,
  color: "#374151",
  flexShrink: 0,
};

const PLACEHOLDER_STYLE: React.CSSProperties = {
  padding: "20px 14px",
  color: "#9ca3af",
  fontSize: 12,
  lineHeight: 1.5,
};

const SECTION_STYLE: React.CSSProperties = {
  padding: "10px 14px",
  borderBottom: "1px solid #f3f4f6",
};

const SECTION_TITLE_STYLE: React.CSSProperties = {
  fontWeight: 600,
  fontSize: 11,
  color: "#6b7280",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  marginBottom: 6,
};

const VALUE_STYLE: React.CSSProperties = {
  color: "#111827",
  lineHeight: 1.5,
};

const CODE_STYLE: React.CSSProperties = {
  display: "block",
  fontFamily: "monospace",
  fontSize: 11,
  backgroundColor: "#f9fafb",
  border: "1px solid #e5e7eb",
  borderRadius: 4,
  padding: "6px 8px",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  lineHeight: 1.6,
  color: "#374151",
};

const MONO_STYLE: React.CSSProperties = {
  fontFamily: "monospace",
  fontSize: 11,
  backgroundColor: "#f3f4f6",
  padding: "1px 4px",
  borderRadius: 3,
  color: "#374151",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={SECTION_STYLE}>
      <div style={SECTION_TITLE_STYLE}>{title}</div>
      <div style={VALUE_STYLE}>{children}</div>
    </div>
  );
}

function RuleDetailView({ rule }: { rule: RuleDetail }) {
  return (
    <>
      <Section title="Summary">
        {rule.name && <div style={{ color: "#374151" }}>{rule.name}</div>}
        <div style={{ marginTop: rule.name ? 4 : 0, color: "#6b7280", fontSize: 11 }}>
          Index: {rule.index}
        </div>
      </Section>

      <Section title="Condition">
        <code style={CODE_STYLE}>{rule.condition_text}</code>
      </Section>

      <Section title="Action">
        <div>{rule.action_text || <span style={{ color: "#9ca3af" }}>(none)</span>}</div>
      </Section>

      <Section title="Flow Behavior">
        <div>
          On match:{" "}
          <span
            style={{
              ...MONO_STYLE,
              backgroundColor: rule.on_match === "continue" ? "#fef9c3" : "#f0fdf4",
              color: rule.on_match === "continue" ? "#713f12" : "#14532d",
            }}
          >
            {rule.on_match}
          </span>
        </div>
      </Section>

      {rule.linked_names.length > 0 && (
        <Section title="Linked References">
          <ul style={{ margin: 0, paddingLeft: 16, lineHeight: 1.8 }}>
            {rule.linked_names.map((n, i) => (
              <li key={i} style={{ color: "#374151" }}>
                {n}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

export default function PolicyDetailsPanel({ details, selectedNode }: PolicyDetailsPanelProps) {
  return (
    <div style={PANEL_STYLE}>
      <div style={HEADER_STYLE}>Policy Inspector</div>

      {selectedNode === null ? (
        <div style={PLACEHOLDER_STYLE}>Click a node to inspect its policy details.</div>
      ) : selectedNode.trace_rule_id === "" ? (
        <div style={PLACEHOLDER_STYLE}>
          <div style={{ fontWeight: 600, color: "#374151", marginBottom: 6 }}>
            {selectedNode.type.charAt(0).toUpperCase() + selectedNode.type.slice(1)} node
          </div>
          <div>{selectedNode.label.split("\n")[0]}</div>
          <div style={{ marginTop: 8 }}>No policy rule is linked to this structural node.</div>
        </div>
      ) : !details || !(selectedNode.trace_rule_id in details.rule_index) ? (
        <div style={PLACEHOLDER_STYLE}>
          <div style={{ fontWeight: 600, color: "#dc2626", marginBottom: 6 }}>
            Rule not found
          </div>
          <div>Details for this node could not be resolved.</div>
        </div>
      ) : (
        <RuleDetailView rule={details.rule_index[selectedNode.trace_rule_id]} />
      )}
    </div>
  );
}
