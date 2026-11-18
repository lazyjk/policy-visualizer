import type { FlowNode, PolicyDetails, ProfileDetail, RuleDetail, ServiceContext } from "../api";
import { templateLabel } from "../serviceLabels";

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

function Pill({ text, tone }: { text: string; tone: "green" | "gray" | "amber" | "red" | "blue" }) {
  const tones = {
    green: { bg: "#dcfce7", fg: "#14532d" },
    gray: { bg: "#f3f4f6", fg: "#4b5563" },
    amber: { bg: "#fef3c7", fg: "#78350f" },
    red: { bg: "#fee2e2", fg: "#7f1d1d" },
    blue: { bg: "#dbeafe", fg: "#1e3a8a" },
  }[tone];
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 10,
        fontWeight: 600,
        padding: "1px 6px",
        borderRadius: 9,
        backgroundColor: tones.bg,
        color: tones.fg,
        marginRight: 4,
        marginBottom: 2,
        whiteSpace: "nowrap",
      }}
    >
      {text}
    </span>
  );
}

function profileTone(p: ProfileDetail): "green" | "red" | "blue" | "gray" {
  if (/reject|deny|fail/.test(p.profile_type) || /reject|deny|drop/.test(p.action)) return "red";
  if (p.profile_type === "radius_coa" || p.profile_type === "post_auth") return "blue";
  if (/accept/.test(p.profile_type)) return "green";
  return "gray";
}

function isDur(p: ProfileDetail): boolean {
  return (p.product ?? "").toLowerCase().startsWith("dur")
    || p.attributes.some((a) => a.type.startsWith("DUR"));
}

function ProfilesSection({ profiles }: { profiles: ProfileDetail[] }) {
  if (profiles.length === 0) return null;
  return (
    <Section title="Enforcement Profiles">
      {profiles.map((p, i) => (
        <div key={i} style={{ marginBottom: i < profiles.length - 1 ? 10 : 0 }}>
          <div style={{ fontWeight: 600, color: "#111827", marginBottom: 3 }}>{p.name}</div>
          <div style={{ marginBottom: 4 }}>
            <Pill text={p.profile_type.replace(/_/g, " ")} tone={profileTone(p)} />
            {p.action && <Pill text={p.action} tone="gray" />}
            {p.template && <Pill text={`template: ${p.template}`} tone="gray" />}
            {isDur(p) && <Pill text="Downloadable Role" tone="blue" />}
          </div>
          {(p.nad_groups ?? []).length > 0 && (
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>
              NAD groups: <span style={{ color: "#374151" }}>{p.nad_groups.join(", ")}</span>
            </div>
          )}
          {p.attributes.length > 0 ? (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <tbody>
                {p.attributes.map((a, j) => (
                  <tr key={j} style={{ borderTop: "1px solid #f3f4f6", verticalAlign: "top" }}>
                    <td style={{ padding: "3px 6px 3px 0", width: "45%" }}>
                      <div style={{ color: "#374151", wordBreak: "break-word" }}>{a.name}</div>
                      {a.type && <div style={{ color: "#9ca3af", fontSize: 10 }}>{a.type}</div>}
                    </td>
                    <td style={{ padding: "3px 0", fontFamily: "monospace", color: "#111827", wordBreak: "break-word" }}>
                      {a.display_value || a.value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ color: "#9ca3af", fontSize: 11 }}>No attributes in export</div>
          )}
        </div>
      ))}
    </Section>
  );
}

function ServiceSummaryCard({ ctx }: { ctx: ServiceContext }) {
  const flags: string[] = [];
  if (ctx.use_cached_results) flags.push("Cached results");
  if (ctx.posture_enabled) flags.push("Posture");
  if (ctx.profiler_enabled) flags.push("Profiler");
  if (ctx.audit_enabled) flags.push("Audit");
  const tmpl = templateLabel(ctx.template);
  return (
    <>
      <Section title="Service">
        <div style={{ fontWeight: 600, color: "#111827" }}>{ctx.service_name}</div>
        {ctx.description && <div style={{ color: "#6b7280", fontSize: 12, marginTop: 2 }}>{ctx.description}</div>}
        <div style={{ marginTop: 6 }}>
          <Pill text={ctx.service_type} tone="gray" />
          {tmpl && <Pill text={tmpl} tone="gray" />}
          <Pill text={ctx.enabled ? "Enabled" : "Disabled"} tone={ctx.enabled ? "green" : "red"} />
          {ctx.monitor_mode && <Pill text="Monitor mode" tone="amber" />}
        </div>
        {flags.length > 0 && (
          <div style={{ marginTop: 4 }}>
            {flags.map((f) => <Pill key={f} text={f} tone="blue" />)}
          </div>
        )}
      </Section>

      {(ctx.auth_method_names.length > 0 || ctx.auth_source_names.length > 0) && (
        <Section title="Authentication">
          {ctx.auth_method_names.length > 0 && (
            <div><span style={{ color: "#6b7280" }}>Methods: </span>{ctx.auth_method_names.join(", ")}</div>
          )}
          {ctx.auth_source_names.length > 0 && (
            <div><span style={{ color: "#6b7280" }}>Sources: </span>{ctx.auth_source_names.join(", ")}</div>
          )}
        </Section>
      )}

      {(ctx.role_mapping_policy_name || ctx.enforcement_policy_name) && (
        <Section title="Policies">
          {ctx.role_mapping_policy_name && (
            <div><span style={{ color: "#6b7280" }}>Role mapping: </span>{ctx.role_mapping_policy_name}</div>
          )}
          {ctx.enforcement_policy_name && (
            <div><span style={{ color: "#6b7280" }}>Enforcement: </span>{ctx.enforcement_policy_name}</div>
          )}
        </Section>
      )}

      <Section title="Service Match">
        <code style={CODE_STYLE}>{ctx.condition_text}</code>
      </Section>

      <div style={PLACEHOLDER_STYLE}>Click a node to inspect its policy details.</div>
    </>
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

      <ProfilesSection profiles={rule.profiles ?? []} />

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
        details ? (
          <ServiceSummaryCard ctx={details.service_context} />
        ) : (
          <div style={PLACEHOLDER_STYLE}>Click a node to inspect its policy details.</div>
        )
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
