/**
 * NewServiceWizard — 3-step modal for creating a new service skeleton.
 *
 * Step 1: Service name + type + description
 * Step 2: Service match conditions (via ConditionBuilder)
 * Step 3: Authentication methods + sources
 *
 * On finish: calls onComplete with a CanvasState that populates the canvas.
 */
import { useState } from "react";
import { v4 as uuidv4 } from "uuid";
import type {
  CanvasState,
  BuilderAuthItem,
  ClearPassElements,
  ClearPassCredentials,
  BuilderConditionExpr,
} from "../../api/builderApi";
import ConditionBuilder from "./ConditionBuilder";

interface Props {
  elements: ClearPassElements;
  creds: ClearPassCredentials | null;
  onComplete: (state: CanvasState) => void;
  onCancel: () => void;
  initialName?: string;
  initialServiceType?: "RADIUS" | "TACACS";
}

const STEP_LABELS = ["Service Details", "Match Conditions", "Authentication"];

export default function NewServiceWizard({ elements, creds, onComplete, onCancel, initialName, initialServiceType }: Props) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState(initialName ?? "");
  const [serviceType, setServiceType] = useState<"RADIUS" | "TACACS">(initialServiceType ?? "RADIUS");
  const [description, setDescription] = useState("");
  const [matchExpr, setMatchExpr] = useState<BuilderConditionExpr | null>(null);
  const [selectedMethods, setSelectedMethods] = useState<BuilderAuthItem[]>([]);
  const [selectedSources, setSelectedSources] = useState<BuilderAuthItem[]>([]);

  function canAdvance() {
    if (step === 0) return name.trim().length > 0;
    return true;
  }

  function handleFinish() {
    const rmId = uuidv4();
    const epId = uuidv4();

    const state: CanvasState = {
      service: {
        name: name.trim(),
        serviceType,
        description: description.trim(),
        match: matchExpr,
      },
      auth: {
        methods: selectedMethods,
        sources: selectedSources,
      },
      roleMappingPolicy: {
        id: rmId,
        name: `${name.trim()} Role Mapping`,
        rules: [],
        defaultRoleId: "",
        defaultRoleName: "",
      },
      enforcementPolicy: {
        id: epId,
        name: `${name.trim()} Enforcement`,
        rules: [],
        defaultProfileIds: [],
        defaultProfileNames: [],
      },
      roles: elements.roles.map((r) => ({
        id: String(r.id ?? r.name ?? uuidv4()),
        name: String(r.name ?? "(unnamed)"),
      })),
      enforcementProfiles: elements.enforcement_profiles.map((p) => ({
        id: String(p.id ?? p.name ?? uuidv4()),
        name: String(p.name ?? "(unnamed)"),
        profile_type: String(p.profile_type ?? "radius_accept"),
      })),
    };
    onComplete(state);
  }

  const authMethods = elements.auth_methods;
  const authSources = elements.auth_sources;

  function toggleMethod(item: { id: string; name: string }) {
    setSelectedMethods((prev) =>
      prev.some((m) => m.id === item.id)
        ? prev.filter((m) => m.id !== item.id)
        : [...prev, { id: item.id, name: item.name }]
    );
  }

  function toggleSource(item: { id: string; name: string }) {
    setSelectedSources((prev) =>
      prev.some((s) => s.id === item.id)
        ? prev.filter((s) => s.id !== item.id)
        : [...prev, { id: item.id, name: item.name }]
    );
  }

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.4)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 1000,
    }}>
      <div style={{
        background: "#fff",
        borderRadius: 10,
        width: 560,
        maxHeight: "85vh",
        display: "flex",
        flexDirection: "column",
        boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
        fontFamily: "Helvetica, Arial, sans-serif",
      }}>
        {/* Header */}
        <div style={{ padding: "20px 24px 0" }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#111827", marginBottom: 16 }}>
            New Service
          </div>

          {/* Step indicator */}
          <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 24 }}>
            {STEP_LABELS.map((label, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", flex: 1 }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: 1 }}>
                  <div style={{
                    width: 28,
                    height: 28,
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 12,
                    fontWeight: 700,
                    background: i < step ? "#3b82f6" : i === step ? "#eff6ff" : "#f3f4f6",
                    color: i < step ? "#fff" : i === step ? "#3b82f6" : "#9ca3af",
                    border: i === step ? "2px solid #3b82f6" : i < step ? "none" : "2px solid #e5e7eb",
                  }}>
                    {i < step ? "✓" : i + 1}
                  </div>
                  <div style={{
                    fontSize: 11,
                    marginTop: 4,
                    color: i === step ? "#3b82f6" : "#9ca3af",
                    fontWeight: i === step ? 600 : 400,
                    whiteSpace: "nowrap",
                  }}>
                    {label}
                  </div>
                </div>
                {i < STEP_LABELS.length - 1 && (
                  <div style={{
                    height: 2,
                    flex: 1,
                    background: i < step ? "#3b82f6" : "#e5e7eb",
                    marginBottom: 18,
                  }} />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Body */}
        <div style={{ padding: "0 24px", flex: 1, overflowY: "auto" }}>
          {step === 0 && (
            <Step1
              name={name}
              serviceType={serviceType}
              description={description}
              onNameChange={setName}
              onTypeChange={setServiceType}
              onDescriptionChange={setDescription}
            />
          )}
          {step === 1 && (
            <Step2
              matchExpr={matchExpr}
              onChange={setMatchExpr}
              creds={creds}
              serviceType={serviceType}
            />
          )}
          {step === 2 && (
            <Step3
              authMethods={authMethods}
              authSources={authSources}
              selectedMethods={selectedMethods}
              selectedSources={selectedSources}
              onToggleMethod={toggleMethod}
              onToggleSource={toggleSource}
            />
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: "16px 24px",
          borderTop: "1px solid #e5e7eb",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}>
          <button onClick={onCancel} style={cancelBtnStyle}>Cancel</button>
          <div style={{ display: "flex", gap: 8 }}>
            {step > 0 && (
              <button onClick={() => setStep(step - 1)} style={secondaryBtnStyle}>
                Back
              </button>
            )}
            {step < STEP_LABELS.length - 1 ? (
              <button
                onClick={() => setStep(step + 1)}
                disabled={!canAdvance()}
                style={{ ...primaryBtnStyle, opacity: canAdvance() ? 1 : 0.4, cursor: canAdvance() ? "pointer" : "default" }}
              >
                Next
              </button>
            ) : (
              <button onClick={handleFinish} style={primaryBtnStyle}>
                Create Service
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1: Service details
// ---------------------------------------------------------------------------

function Step1({
  name,
  serviceType,
  description,
  onNameChange,
  onTypeChange,
  onDescriptionChange,
}: {
  name: string;
  serviceType: "RADIUS" | "TACACS";
  description: string;
  onNameChange: (v: string) => void;
  onTypeChange: (v: "RADIUS" | "TACACS") => void;
  onDescriptionChange: (v: string) => void;
}) {
  return (
    <div>
      <Field label="Service Name *">
        <input
          autoFocus
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="e.g. Corp Wireless 802.1X"
          style={inputStyle}
        />
      </Field>
      <Field label="Service Type">
        <div style={{ display: "flex", gap: 8 }}>
          {(["RADIUS", "TACACS"] as const).map((t) => (
            <button
              key={t}
              onClick={() => onTypeChange(t)}
              style={{
                padding: "8px 20px",
                borderRadius: 5,
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                fontFamily: "Helvetica, Arial, sans-serif",
                background: serviceType === t ? "#3b82f6" : "#f3f4f6",
                color: serviceType === t ? "#fff" : "#374151",
                border: serviceType === t ? "none" : "1px solid #d1d5db",
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </Field>
      <Field label="Description">
        <textarea
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          placeholder="Optional description"
          rows={3}
          style={{ ...inputStyle, resize: "vertical" }}
        />
      </Field>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2: Match conditions
// ---------------------------------------------------------------------------

function Step2({
  matchExpr,
  onChange,
  creds,
  serviceType,
}: {
  matchExpr: BuilderConditionExpr | null;
  onChange: (expr: BuilderConditionExpr | null) => void;
  creds: ClearPassCredentials | null;
  serviceType: "RADIUS" | "TACACS";
}) {
  return (
    <div>
      <p style={{ fontSize: 13, color: "#6b7280", marginTop: 0, marginBottom: 16 }}>
        Define which traffic this service matches. Leave empty to match all.
      </p>
      <ConditionBuilder
        expr={matchExpr}
        onChange={onChange}
        creds={creds}
        serviceType={serviceType}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3: Authentication
// ---------------------------------------------------------------------------

function Step3({
  authMethods,
  authSources,
  selectedMethods,
  selectedSources,
  onToggleMethod,
  onToggleSource,
}: {
  authMethods: { id: string; name: string }[];
  authSources: { id: string; name: string }[];
  selectedMethods: BuilderAuthItem[];
  selectedSources: BuilderAuthItem[];
  onToggleMethod: (item: { id: string; name: string }) => void;
  onToggleSource: (item: { id: string; name: string }) => void;
}) {
  return (
    <div>
      <p style={{ fontSize: 13, color: "#6b7280", marginTop: 0, marginBottom: 16 }}>
        Select authentication methods and sources. You can modify these later.
      </p>
      <Field label={`Auth Methods (${selectedMethods.length} selected)`}>
        <SelectableList
          items={authMethods}
          selectedIds={selectedMethods.map((m) => m.id)}
          onToggle={onToggleMethod}
          emptyLabel="No auth methods available"
        />
      </Field>
      <Field label={`Auth Sources (${selectedSources.length} selected)`}>
        <SelectableList
          items={authSources}
          selectedIds={selectedSources.map((s) => s.id)}
          onToggle={onToggleSource}
          emptyLabel="No auth sources available"
        />
      </Field>
    </div>
  );
}

function SelectableList({
  items,
  selectedIds,
  onToggle,
  emptyLabel,
}: {
  items: { id: string; name: string }[];
  selectedIds: string[];
  onToggle: (item: { id: string; name: string }) => void;
  emptyLabel: string;
}) {
  if (items.length === 0) {
    return <div style={{ fontSize: 12, color: "#9ca3af", fontStyle: "italic" }}>{emptyLabel}</div>;
  }
  return (
    <div style={{
      maxHeight: 200,
      overflowY: "auto",
      border: "1px solid #e5e7eb",
      borderRadius: 5,
    }}>
      {items.map((item, i) => {
        const id = item.id;
        const name = item.name;
        const selected = selectedIds.includes(id);
        return (
          <div
            key={id}
            onClick={() => onToggle(item)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "7px 12px",
              cursor: "pointer",
              background: selected ? "#eff6ff" : "#fff",
              borderBottom: i < items.length - 1 ? "1px solid #f3f4f6" : "none",
              userSelect: "none",
            }}
          >
            <div style={{
              width: 16,
              height: 16,
              borderRadius: 4,
              border: selected ? "none" : "2px solid #d1d5db",
              background: selected ? "#3b82f6" : "transparent",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}>
              {selected && <span style={{ color: "#fff", fontSize: 10, lineHeight: 1 }}>✓</span>}
            </div>
            <span style={{ fontSize: 13, color: "#111827" }}>{name}</span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 6 }}>
        {label}
      </label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: "8px 12px",
  border: "1px solid #d1d5db",
  borderRadius: 5,
  fontSize: 13,
  fontFamily: "Helvetica, Arial, sans-serif",
  background: "#fff",
};

const primaryBtnStyle: React.CSSProperties = {
  padding: "8px 20px",
  background: "#3b82f6",
  color: "#fff",
  border: "none",
  borderRadius: 5,
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
  fontFamily: "Helvetica, Arial, sans-serif",
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: "8px 20px",
  background: "#f3f4f6",
  color: "#374151",
  border: "none",
  borderRadius: 5,
  fontSize: 13,
  fontWeight: 500,
  cursor: "pointer",
  fontFamily: "Helvetica, Arial, sans-serif",
};

const cancelBtnStyle: React.CSSProperties = {
  padding: "8px 16px",
  background: "none",
  color: "#6b7280",
  border: "none",
  borderRadius: 5,
  fontSize: 13,
  cursor: "pointer",
  fontFamily: "Helvetica, Arial, sans-serif",
};
