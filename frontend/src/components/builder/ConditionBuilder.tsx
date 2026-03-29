/**
 * ConditionBuilder — flat AND/OR list of predicates.
 *
 * Fetches the ClearPass attribute dictionary on first mount (when creds supplied).
 * Each predicate row: namespace → attribute → operator → value.
 */
import { useEffect, useState, useCallback } from "react";
import type { BuilderConditionExpr, BuilderCondition, ClearPassCredentials, AttributeDict } from "../../api/builderApi";
import { fetchClearPassAttributes } from "../../api/builderApi";

const OPERATORS = [
  { value: "equals", label: "equals" },
  { value: "not_equals", label: "not equals" },
  { value: "contains", label: "contains" },
  { value: "not_contains", label: "not contains" },
  { value: "starts_with", label: "starts with" },
  { value: "ends_with", label: "ends with" },
  { value: "regex", label: "matches regex" },
  { value: "in", label: "in list" },
  { value: "exists", label: "exists" },
  { value: "not_exists", label: "not exists" },
  { value: "less_than", label: "less than" },
  { value: "greater_than", label: "greater than" },
  { value: "belongs_to_group", label: "belongs to group" },
];

const EMPTY_EXPR: BuilderConditionExpr = { combinator: "and", conditions: [] };

interface Props {
  expr: BuilderConditionExpr | null;
  onChange: (expr: BuilderConditionExpr | null) => void;
  creds: ClearPassCredentials | null;
  serviceType: "RADIUS" | "TACACS";
}

export default function ConditionBuilder({ expr, onChange, creds, serviceType }: Props) {
  const [attrDict, setAttrDict] = useState<AttributeDict | null>(null);
  const [attrLoading, setAttrLoading] = useState(false);
  const [attrError, setAttrError] = useState<string | null>(null);

  useEffect(() => {
    if (!creds || attrDict) return;
    setAttrLoading(true);
    setAttrError(null);
    fetchClearPassAttributes(creds)
      .then((d) => setAttrDict(d))
      .catch((e: unknown) => setAttrError(e instanceof Error ? e.message : String(e)))
      .finally(() => setAttrLoading(false));
  }, [creds, attrDict]);

  const current = expr ?? EMPTY_EXPR;

  const updateCondition = useCallback(
    (idx: number, patch: Partial<BuilderCondition>) => {
      const updated = [...current.conditions];
      updated[idx] = { ...updated[idx], ...patch };
      onChange({ ...current, conditions: updated });
    },
    [current, onChange]
  );

  const addCondition = useCallback(() => {
    const newCond: BuilderCondition = { namespace: "", attribute: "", op: "equals", value: "" };
    onChange({ ...current, conditions: [...current.conditions, newCond] });
  }, [current, onChange]);

  const removeCondition = useCallback(
    (idx: number) => {
      const updated = current.conditions.filter((_, i) => i !== idx);
      if (updated.length === 0) {
        onChange(null);
      } else {
        onChange({ ...current, conditions: updated });
      }
    },
    [current, onChange]
  );

  // Derive namespace list based on service type.
  // RADIUS services: exclude TACACS-specific namespaces.
  // TACACS services: exclude RADIUS-specific namespaces.
  const namespaces = attrDict
    ? Object.keys(attrDict.namespaces).filter((ns) => {
        const lower = ns.toLowerCase();
        if (serviceType === "TACACS") return !lower.startsWith("radius:");
        if (serviceType === "RADIUS") return lower !== "tacacs" && !lower.startsWith("tacacs:");
        return true;
      })
    : [];

  return (
    <div>
      {/* Combinator toggle */}
      {current.conditions.length > 1 && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
          <span style={{ fontSize: 11, color: "#6b7280" }}>Match:</span>
          {(["and", "or"] as const).map((v) => (
            <button
              key={v}
              onClick={() => onChange({ ...current, combinator: v })}
              style={{
                padding: "2px 10px",
                borderRadius: 4,
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
                fontFamily: "Helvetica, Arial, sans-serif",
                background: current.combinator === v ? "#3b82f6" : "#f9fafb",
                color: current.combinator === v ? "#fff" : "#374151",
                border: current.combinator === v ? "none" : "1px solid #e5e7eb",
              }}
            >
              {v === "and" ? "ALL conditions" : "ANY condition"}
            </button>
          ))}
        </div>
      )}

      {/* Condition rows */}
      {current.conditions.map((cond, idx) => (
        <ConditionRow
          key={idx}
          cond={cond}
          namespaces={namespaces}
          attrDict={attrDict}
          onChange={(patch) => updateCondition(idx, patch)}
          onDelete={() => removeCondition(idx)}
        />
      ))}

      {/* Attribute loading state */}
      {attrLoading && (
        <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 6 }}>Loading attributes…</div>
      )}
      {attrError && (
        <div style={{ fontSize: 11, color: "#dc2626", marginBottom: 6 }}>
          Could not load attributes: {attrError}
        </div>
      )}
      {!creds && (
        <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 6 }}>
          Connect to ClearPass to get attribute suggestions
        </div>
      )}

      <button onClick={addCondition} style={addCondBtnStyle}>
        + Add condition
      </button>

      {current.conditions.length > 0 && (
        <button
          onClick={() => onChange(null)}
          style={{ ...addCondBtnStyle, marginLeft: 8, color: "#dc2626", borderColor: "#fca5a5" }}
        >
          Clear all
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single condition row
// ---------------------------------------------------------------------------

interface RowProps {
  cond: BuilderCondition;
  namespaces: string[];
  attrDict: AttributeDict | null;
  onChange: (patch: Partial<BuilderCondition>) => void;
  onDelete: () => void;
}

function ConditionRow({ cond, namespaces, attrDict, onChange, onDelete }: RowProps) {
  const attributes = attrDict?.namespaces[cond.namespace] ?? [];
  const noValueOps = new Set(["exists", "not_exists"]);

  return (
    <div style={{
      display: "flex",
      flexWrap: "wrap",
      gap: 4,
      alignItems: "center",
      marginBottom: 6,
      padding: "6px 8px",
      background: "#f9fafb",
      borderRadius: 5,
      border: "1px solid #e5e7eb",
    }}>
      {/* Namespace */}
      {namespaces.length > 0 ? (
        <select
          value={cond.namespace}
          onChange={(e) => onChange({ namespace: e.target.value, attribute: "" })}
          style={selectStyle}
        >
          <option value="">Namespace…</option>
          {/* Preserve a loaded value that isn't in the dict (e.g. Authorization:SourceName) */}
          {cond.namespace && !namespaces.includes(cond.namespace) && (
            <option value={cond.namespace}>{cond.namespace}</option>
          )}
          {namespaces.map((ns) => <option key={ns} value={ns}>{ns}</option>)}
        </select>
      ) : (
        <input
          value={cond.namespace}
          onChange={(e) => onChange({ namespace: e.target.value })}
          placeholder="Namespace"
          style={{ ...inputStyle, width: 100 }}
        />
      )}

      {/* Attribute */}
      {attributes.length > 0 ? (
        <select
          value={cond.attribute}
          onChange={(e) => onChange({ attribute: e.target.value })}
          style={selectStyle}
        >
          <option value="">Attribute…</option>
          {/* Preserve a loaded value that isn't in the dict */}
          {cond.attribute && !attributes.includes(cond.attribute) && (
            <option value={cond.attribute}>{cond.attribute}</option>
          )}
          {attributes.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
      ) : (
        <input
          value={cond.attribute}
          onChange={(e) => onChange({ attribute: e.target.value })}
          placeholder="Attribute"
          style={{ ...inputStyle, width: 120 }}
        />
      )}

      {/* Operator */}
      <select
        value={cond.op}
        onChange={(e) => onChange({ op: e.target.value })}
        style={selectStyle}
      >
        {OPERATORS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>

      {/* Value */}
      {!noValueOps.has(cond.op) && (
        <input
          value={cond.value}
          onChange={(e) => onChange({ value: e.target.value })}
          placeholder="value"
          style={{ ...inputStyle, width: 100 }}
        />
      )}

      {/* Delete */}
      <button
        onClick={onDelete}
        style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", fontSize: 14, padding: "0 2px", lineHeight: 1 }}
        title="Remove condition"
      >
        ×
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------

const selectStyle: React.CSSProperties = {
  padding: "4px 6px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  fontSize: 12,
  fontFamily: "Helvetica, Arial, sans-serif",
  background: "#fff",
};

const inputStyle: React.CSSProperties = {
  padding: "4px 6px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  fontSize: 12,
  fontFamily: "Helvetica, Arial, sans-serif",
  background: "#fff",
};

const addCondBtnStyle: React.CSSProperties = {
  padding: "4px 10px",
  background: "#fff",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  fontSize: 12,
  cursor: "pointer",
  fontFamily: "Helvetica, Arial, sans-serif",
  color: "#374151",
  marginTop: 4,
};
