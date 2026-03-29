/**
 * RuleEditor — rule list editor for Role Mapping and Enforcement policies.
 *
 * Renders a numbered list of rules. Each rule has:
 *  - A ConditionBuilder for the "when" clause
 *  - An action picker (role for roleMapping, profile(s) for enforcement)
 *  - on-match toggle (stop / continue)
 *  - Delete button
 *
 * A "Default" row at the bottom has no condition.
 */
import { useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import type {
  BuilderRule,
  CanvasRoleItem,
  CanvasProfileItem,
  ClearPassCredentials,
} from "../../api/builderApi";
import ConditionBuilder from "./ConditionBuilder";

interface BaseProps {
  rules: BuilderRule[];
  roles: CanvasRoleItem[];
  enforcementProfiles: CanvasProfileItem[];
  creds: ClearPassCredentials | null;
  serviceType: "RADIUS" | "TACACS";
  onRulesChange: (rules: BuilderRule[]) => void;
}

interface RoleMappingProps extends BaseProps {
  type: "roleMapping";
  defaultRoleId: string;
  defaultRoleName: string;
  defaultProfileIds?: never;
  defaultProfileNames?: never;
  onDefaultChange: (roleId: string, roleName: string) => void;
}

interface EnforcementProps extends BaseProps {
  type: "enforcement";
  defaultProfileIds: string[];
  defaultProfileNames: string[];
  defaultRoleId?: never;
  defaultRoleName?: never;
  onDefaultChange: (profileIds: string[], profileNames: string[]) => void;
}

type Props = RoleMappingProps | EnforcementProps;

export default function RuleEditor(props: Props) {
  const { rules, roles, enforcementProfiles, creds, serviceType, onRulesChange, type } = props;

  const addRule = useCallback(() => {
    const newRule: BuilderRule = {
      id: uuidv4(),
      name: `Rule ${rules.length + 1}`,
      condition: { combinator: "and", conditions: [] },
      on_match: "stop",
    };
    if (type === "roleMapping") {
      newRule.role_action = { role_id: "", role_name: "" };
    } else {
      newRule.enforcement_action = { profile_ids: [], profile_names: [] };
    }
    onRulesChange([...rules, newRule]);
  }, [rules, type, onRulesChange]);

  const updateRule = useCallback(
    (idx: number, patch: Partial<BuilderRule>) => {
      const updated = [...rules];
      updated[idx] = { ...updated[idx], ...patch };
      onRulesChange(updated);
    },
    [rules, onRulesChange]
  );

  const removeRule = useCallback(
    (idx: number) => {
      onRulesChange(rules.filter((_, i) => i !== idx));
    },
    [rules, onRulesChange]
  );

  const moveRule = useCallback(
    (idx: number, direction: -1 | 1) => {
      const target = idx + direction;
      if (target < 0 || target >= rules.length) return;
      const updated = [...rules];
      [updated[idx], updated[target]] = [updated[target], updated[idx]];
      onRulesChange(updated);
    },
    [rules, onRulesChange]
  );

  return (
    <div>
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 8,
      }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5 }}>
          Rules ({rules.length})
        </span>
        <button onClick={addRule} style={addBtnStyle}>
          + Add Rule
        </button>
      </div>

      {rules.length === 0 && (
        <div style={{ fontSize: 12, color: "#9ca3af", fontStyle: "italic", marginBottom: 12 }}>
          No rules yet — add one above.
        </div>
      )}

      {rules.map((rule, idx) => (
        <RuleRow
          key={rule.id}
          index={idx}
          rule={rule}
          type={type}
          roles={roles}
          profiles={enforcementProfiles}
          isFirst={idx === 0}
          isLast={idx === rules.length - 1}
          creds={creds}
          serviceType={serviceType}
          onChange={(patch) => updateRule(idx, patch)}
          onDelete={() => removeRule(idx)}
          onMove={(dir) => moveRule(idx, dir)}
        />
      ))}

      {/* Default row */}
      <div style={{
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        padding: "10px 12px",
        marginTop: 8,
        background: "#f9fafb",
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
          Default (no match)
        </div>
        {type === "roleMapping" ? (
          <RolePicker
            roleId={props.defaultRoleId}
            roleName={props.defaultRoleName}
            roles={roles}
            onChange={(id, name) => (props as RoleMappingProps).onDefaultChange(id, name)}
          />
        ) : (
          <ProfilePicker
            profileIds={props.defaultProfileIds}
            profileNames={props.defaultProfileNames}
            profiles={enforcementProfiles}
            onChange={(ids, names) => (props as EnforcementProps).onDefaultChange(ids, names)}
          />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single rule row
// ---------------------------------------------------------------------------

interface RuleRowProps {
  index: number;
  rule: BuilderRule;
  type: "roleMapping" | "enforcement";
  roles: CanvasRoleItem[];
  profiles: CanvasProfileItem[];
  isFirst: boolean;
  isLast: boolean;
  creds: ClearPassCredentials | null;
  serviceType: "RADIUS" | "TACACS";
  onChange: (patch: Partial<BuilderRule>) => void;
  onDelete: () => void;
  onMove: (dir: -1 | 1) => void;
}

function RuleRow({ index, rule, type, roles, profiles, isFirst, isLast, creds, serviceType, onChange, onDelete, onMove }: RuleRowProps) {
  return (
    <div style={{
      border: "1px solid #e5e7eb",
      borderRadius: 6,
      marginBottom: 8,
      background: "#fff",
      overflow: "hidden",
    }}>
      {/* Row header */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 10px",
        borderBottom: "1px solid #f3f4f6",
        background: "#f9fafb",
      }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#9ca3af", minWidth: 20 }}>
          {index + 1}
        </span>
        <input
          value={rule.name}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder={`Rule ${index + 1}`}
          style={{
            flex: 1,
            border: "none",
            background: "transparent",
            fontSize: 12,
            fontWeight: 600,
            color: "#374151",
            fontFamily: "Helvetica, Arial, sans-serif",
            outline: "none",
          }}
        />
        <button onClick={() => onMove(-1)} disabled={isFirst} style={iconBtnStyle} title="Move up">↑</button>
        <button onClick={() => onMove(1)} disabled={isLast} style={iconBtnStyle} title="Move down">↓</button>
        <button onClick={onDelete} style={{ ...iconBtnStyle, color: "#ef4444" }} title="Delete rule">×</button>
      </div>

      {/* Condition */}
      <div style={{ padding: "8px 10px", borderBottom: "1px solid #f3f4f6" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
          When
        </div>
        <ConditionBuilder
          expr={rule.condition}
          onChange={(condition) => onChange({ condition })}
          creds={creds}
          serviceType={serviceType}
        />
      </div>

      {/* Action */}
      <div style={{ padding: "8px 10px", borderBottom: "1px solid #f3f4f6" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
          Then
        </div>
        {type === "roleMapping" ? (
          <RolePicker
            roleId={rule.role_action?.role_id ?? ""}
            roleName={rule.role_action?.role_name ?? ""}
            roles={roles}
            onChange={(id, name) => onChange({ role_action: { role_id: id, role_name: name } })}
          />
        ) : (
          <ProfilePicker
            profileIds={rule.enforcement_action?.profile_ids ?? []}
            profileNames={rule.enforcement_action?.profile_names ?? []}
            profiles={profiles}
            onChange={(ids, names) => onChange({ enforcement_action: { profile_ids: ids, profile_names: names } })}
          />
        )}
      </div>

      {/* On-match */}
      <div style={{ padding: "6px 10px", display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 11, color: "#6b7280" }}>On match:</span>
        {(["stop", "continue"] as const).map((v) => (
          <button
            key={v}
            onClick={() => onChange({ on_match: v })}
            style={{
              padding: "3px 10px",
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer",
              fontFamily: "Helvetica, Arial, sans-serif",
              background: rule.on_match === v ? (v === "stop" ? "#fef2f2" : "#f0fdf4") : "#f9fafb",
              color: rule.on_match === v ? (v === "stop" ? "#dc2626" : "#16a34a") : "#6b7280",
              border: rule.on_match === v
                ? `1px solid ${v === "stop" ? "#fca5a5" : "#86efac"}`
                : "1px solid #e5e7eb",
            }}
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Role picker
// ---------------------------------------------------------------------------

function RolePicker({
  roleId,
  roleName,
  roles,
  onChange,
}: {
  roleId: string;
  roleName: string;
  roles: CanvasRoleItem[];
  onChange: (id: string, name: string) => void;
}) {
  return (
    <div>
      <span style={{ fontSize: 11, color: "#6b7280", marginRight: 8 }}>Assign role:</span>
      {roles.length === 0 ? (
        <span style={{ fontSize: 12, color: "#9ca3af", fontStyle: "italic" }}>No roles available</span>
      ) : (
        <select
          value={roleId}
          onChange={(e) => {
            const found = roles.find((r) => r.id === e.target.value);
            onChange(e.target.value, found?.name ?? "");
          }}
          style={{
            padding: "4px 8px",
            borderRadius: 4,
            border: "1px solid #d1d5db",
            fontSize: 12,
            fontFamily: "Helvetica, Arial, sans-serif",
            background: "#fff",
          }}
        >
          <option value="">— Select role —</option>
          {roles.map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
      )}
      {!roleId && roleName && (
        <span style={{ fontSize: 11, color: "#9ca3af", marginLeft: 8 }}>{roleName}</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Profile picker
// ---------------------------------------------------------------------------

function ProfilePicker({
  profileIds,
  profileNames,
  profiles,
  onChange,
}: {
  profileIds: string[];
  profileNames: string[];
  profiles: CanvasProfileItem[];
  onChange: (ids: string[], names: string[]) => void;
}) {
  function toggleProfile(id: string, name: string) {
    if (profileIds.includes(id)) {
      const idx = profileIds.indexOf(id);
      onChange(
        profileIds.filter((_, i) => i !== idx),
        profileNames.filter((_, i) => i !== idx)
      );
    } else {
      onChange([...profileIds, id], [...profileNames, name]);
    }
  }

  if (profiles.length === 0) {
    return (
      <div style={{ fontSize: 12, color: "#9ca3af", fontStyle: "italic" }}>
        {profileIds.length > 0
          ? profileNames.join(", ")
          : "No enforcement profiles available"}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {profiles.map((p) => {
        const selected = profileIds.includes(p.id);
        return (
          <button
            key={p.id}
            onClick={() => toggleProfile(p.id, p.name)}
            style={{
              padding: "3px 10px",
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 500,
              cursor: "pointer",
              fontFamily: "Helvetica, Arial, sans-serif",
              background: selected ? "#ede9fe" : "#f9fafb",
              color: selected ? "#7c3aed" : "#374151",
              border: selected ? "1px solid #c4b5fd" : "1px solid #e5e7eb",
            }}
          >
            {p.name}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared button styles
// ---------------------------------------------------------------------------

const addBtnStyle: React.CSSProperties = {
  padding: "4px 10px",
  background: "#fff",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  fontFamily: "Helvetica, Arial, sans-serif",
  color: "#374151",
};

const iconBtnStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  cursor: "pointer",
  padding: "0 4px",
  fontSize: 14,
  color: "#9ca3af",
  fontFamily: "Helvetica, Arial, sans-serif",
};
