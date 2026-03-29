/**
 * BuilderSidePanel — context-aware inspector panel.
 *
 * Shown to the right of the canvas. Content switches based on which
 * node is selected. Rule editing (Phase 2b) is rendered via RuleEditor
 * when a policy node is selected.
 */
import type { CanvasState, CanvasAuthState, ClearPassCredentials } from "../../api/builderApi";
import type { SelectedNodeType } from "./BuilderCanvas";
import RuleEditor from "./RuleEditor";

const PANEL_STYLE: React.CSSProperties = {
  width: 360,
  flexShrink: 0,
  borderLeft: "1px solid #e5e7eb",
  background: "#fff",
  display: "flex",
  flexDirection: "column",
  overflowY: "auto",
  fontFamily: "Helvetica, Arial, sans-serif",
};

const HEADER_STYLE: React.CSSProperties = {
  padding: "12px 16px",
  borderBottom: "1px solid #e5e7eb",
  fontSize: 13,
  fontWeight: 700,
  color: "#374151",
  background: "#f9fafb",
};

const BODY_STYLE: React.CSSProperties = {
  padding: "16px",
  flex: 1,
  overflowY: "auto",
};

interface Props {
  selectedNode: SelectedNodeType;
  canvasState: CanvasState;
  onChange: (updated: CanvasState) => void;
  creds: ClearPassCredentials | null;
}

export default function BuilderSidePanel({ selectedNode, canvasState, onChange, creds }: Props) {
  if (!selectedNode) {
    return (
      <div style={PANEL_STYLE}>
        <div style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#9ca3af",
          fontSize: 13,
          padding: 24,
          textAlign: "center",
        }}>
          Click a node to view and edit its configuration
        </div>
      </div>
    );
  }

  return (
    <div style={PANEL_STYLE}>
      {selectedNode === "service" && (
        <ServicePanel canvasState={canvasState} onChange={onChange} />
      )}
      {selectedNode === "auth" && (
        <AuthPanel canvasState={canvasState} onChange={onChange} />
      )}
      {selectedNode === "roleMapping" && (
        <RoleMappingPanel canvasState={canvasState} onChange={onChange} creds={creds} />
      )}
      {selectedNode === "enforcement" && (
        <EnforcementPanel canvasState={canvasState} onChange={onChange} creds={creds} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Service panel
// ---------------------------------------------------------------------------

function ServicePanel({ canvasState, onChange }: { canvasState: CanvasState; onChange: (s: CanvasState) => void }) {
  const svc = canvasState.service;

  function updateService(patch: Partial<typeof svc>) {
    onChange({ ...canvasState, service: { ...svc, ...patch } });
  }

  return (
    <>
      <div style={HEADER_STYLE}>Service Configuration</div>
      <div style={BODY_STYLE}>
        <Field label="Service Name">
          <input
            value={svc.name}
            onChange={(e) => updateService({ name: e.target.value })}
            style={inputStyle}
          />
        </Field>
        <Field label="Service Type">
          <div style={{ display: "flex", gap: 8 }}>
            {(["RADIUS", "TACACS"] as const).map((t) => (
              <button
                key={t}
                onClick={() => updateService({ serviceType: t })}
                style={{
                  ...typeButtonStyle,
                  background: svc.serviceType === t ? "#3b82f6" : "#f3f4f6",
                  color: svc.serviceType === t ? "#fff" : "#374151",
                  border: svc.serviceType === t ? "none" : "1px solid #d1d5db",
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Description">
          <textarea
            value={svc.description}
            onChange={(e) => updateService({ description: e.target.value })}
            rows={3}
            style={{ ...inputStyle, resize: "vertical" }}
          />
        </Field>
        <Field label="Match Conditions">
          <div style={{ color: "#6b7280", fontSize: 12, fontStyle: "italic" }}>
            {(svc.match?.conditions.length ?? 0) === 0
              ? "No conditions — service will match all traffic"
              : `${svc.match!.conditions.length} condition${svc.match!.conditions.length !== 1 ? "s" : ""} (${svc.match!.combinator.toUpperCase()})`}
          </div>
          <div style={{ marginTop: 8 }}>
            {/* ConditionBuilder will be rendered here in Phase 2b */}
            <ConditionBuilderPlaceholder
              expr={svc.match}
              onChange={(match) => updateService({ match })}
            />
          </div>
        </Field>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Auth panel
// ---------------------------------------------------------------------------

function AuthPanel({ canvasState, onChange }: { canvasState: CanvasState; onChange: (s: CanvasState) => void }) {
  const auth = canvasState.auth;

  function updateAuth(patch: Partial<CanvasAuthState>) {
    onChange({ ...canvasState, auth: { ...auth, ...patch } });
  }

  return (
    <>
      <div style={HEADER_STYLE}>Authentication Configuration</div>
      <div style={BODY_STYLE}>
        <Field label="Auth Methods">
          <ItemListEditor
            items={auth.methods}
            onChange={(methods) => updateAuth({ methods })}
            emptyLabel="No auth methods assigned"
            addLabel="Add method"
          />
        </Field>
        <Field label="Auth Sources">
          <ItemListEditor
            items={auth.sources}
            onChange={(sources) => updateAuth({ sources })}
            emptyLabel="No auth sources assigned"
            addLabel="Add source"
          />
        </Field>
        <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 8, fontStyle: "italic" }}>
          Tip: Drag Auth Methods or Auth Sources from the library on the left onto the canvas to add them here.
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Role Mapping panel
// ---------------------------------------------------------------------------

function RoleMappingPanel({
  canvasState,
  onChange,
  creds,
}: {
  canvasState: CanvasState;
  onChange: (s: CanvasState) => void;
  creds: ClearPassCredentials | null;
}) {
  const rm = canvasState.roleMappingPolicy;

  return (
    <>
      <div style={HEADER_STYLE}>Role Mapping Policy</div>
      <div style={BODY_STYLE}>
        <Field label="Policy Name">
          <input
            value={rm.name}
            onChange={(e) =>
              onChange({
                ...canvasState,
                roleMappingPolicy: { ...rm, name: e.target.value },
              })
            }
            style={inputStyle}
          />
        </Field>
        <RuleEditor
          type="roleMapping"
          rules={rm.rules}
          defaultRoleId={rm.defaultRoleId}
          defaultRoleName={rm.defaultRoleName}
          roles={canvasState.roles}
          enforcementProfiles={canvasState.enforcementProfiles}
          creds={creds}
          serviceType={canvasState.service.serviceType}
          onRulesChange={(rules) =>
            onChange({ ...canvasState, roleMappingPolicy: { ...rm, rules } })
          }
          onDefaultChange={(roleId, roleName) =>
            onChange({
              ...canvasState,
              roleMappingPolicy: { ...rm, defaultRoleId: roleId, defaultRoleName: roleName },
            })
          }
        />
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Enforcement panel
// ---------------------------------------------------------------------------

function EnforcementPanel({
  canvasState,
  onChange,
  creds,
}: {
  canvasState: CanvasState;
  onChange: (s: CanvasState) => void;
  creds: ClearPassCredentials | null;
}) {
  const ep = canvasState.enforcementPolicy;

  return (
    <>
      <div style={HEADER_STYLE}>Enforcement Policy</div>
      <div style={BODY_STYLE}>
        <Field label="Policy Name">
          <input
            value={ep.name}
            onChange={(e) =>
              onChange({
                ...canvasState,
                enforcementPolicy: { ...ep, name: e.target.value },
              })
            }
            style={inputStyle}
          />
        </Field>
        <RuleEditor
          type="enforcement"
          rules={ep.rules}
          defaultProfileIds={ep.defaultProfileIds}
          defaultProfileNames={ep.defaultProfileNames}
          roles={canvasState.roles}
          enforcementProfiles={canvasState.enforcementProfiles}
          creds={creds}
          serviceType={canvasState.service.serviceType}
          onRulesChange={(rules) =>
            onChange({ ...canvasState, enforcementPolicy: { ...ep, rules } })
          }
          onDefaultChange={(profileIds, profileNames) =>
            onChange({
              ...canvasState,
              enforcementPolicy: { ...ep, defaultProfileIds: profileIds, defaultProfileNames: profileNames },
            })
          }
        />
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Small shared sub-components
// ---------------------------------------------------------------------------

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: "#6b7280", marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 }}>
        {label}
      </label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: "7px 10px",
  border: "1px solid #d1d5db",
  borderRadius: 5,
  fontSize: 13,
  fontFamily: "Helvetica, Arial, sans-serif",
  background: "#fff",
};

const typeButtonStyle: React.CSSProperties = {
  padding: "6px 16px",
  borderRadius: 5,
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
  fontFamily: "Helvetica, Arial, sans-serif",
};

interface NamedItem { id: string; name: string }

function ItemListEditor({
  items,
  onChange,
  emptyLabel,
}: {
  items: NamedItem[];
  onChange: (items: NamedItem[]) => void;
  emptyLabel: string;
  addLabel: string;
}) {
  function removeItem(idx: number) {
    onChange(items.filter((_, i) => i !== idx));
  }

  if (items.length === 0) {
    return <div style={{ fontSize: 12, color: "#9ca3af", fontStyle: "italic" }}>{emptyLabel}</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {items.map((item, i) => (
        <div key={item.id} style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "5px 10px",
          background: "#f9fafb",
          borderRadius: 5,
          border: "1px solid #e5e7eb",
        }}>
          <span style={{ fontSize: 13, color: "#111827" }}>{item.name}</span>
          <button
            onClick={() => removeItem(i)}
            style={{
              background: "none",
              border: "none",
              color: "#9ca3af",
              cursor: "pointer",
              fontSize: 14,
              padding: "0 2px",
              lineHeight: 1,
            }}
            title="Remove"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

// Placeholder — replaced by ConditionBuilder in Phase 2b
import type { BuilderConditionExpr } from "../../api/builderApi";

function ConditionBuilderPlaceholder({
  expr,
  onChange,
}: {
  expr: BuilderConditionExpr | null;
  onChange: (expr: BuilderConditionExpr | null) => void;
}) {
  // Minimal placeholder: shows conditions as read-only text with a clear button
  if (!expr || expr.conditions.length === 0) {
    return (
      <div style={{ fontSize: 12, color: "#9ca3af", fontStyle: "italic" }}>
        No conditions — will be configurable in Phase 2b
      </div>
    );
  }
  return (
    <div style={{ fontSize: 12, color: "#374151" }}>
      <div style={{ marginBottom: 4, fontWeight: 600 }}>{expr.combinator.toUpperCase()}</div>
      {expr.conditions.map((c, i) => (
        <div key={i} style={{ padding: "3px 8px", background: "#f3f4f6", borderRadius: 4, marginBottom: 2 }}>
          {c.namespace} · {c.attribute} {c.op} {c.value}
        </div>
      ))}
      <button
        onClick={() => onChange(null)}
        style={{ marginTop: 6, fontSize: 12, color: "#ef4444", background: "none", border: "none", cursor: "pointer", padding: 0 }}
      >
        Clear conditions
      </button>
    </div>
  );
}
