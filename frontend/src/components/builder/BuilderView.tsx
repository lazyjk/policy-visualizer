/**
 * BuilderView — 3-column layout:
 *   Left:   ConnectionPanel + ElementsLibrary (collapsible, 260px)
 *   Center: BuilderCanvas (React Flow)
 *   Right:  BuilderSidePanel (rule editor, shown when node selected)
 */
import { useState } from "react";
import { v4 as uuidv4 } from "uuid";
import ConnectionPanel from "./ConnectionPanel";
import ElementsLibrary from "./ElementsLibrary";
import BuilderCanvas, { type SelectedNodeType } from "./BuilderCanvas";
import BuilderSidePanel from "./BuilderSidePanel";
import NewServiceWizard from "./NewServiceWizard";
import TemplatePickerModal, { type TemplatePolicyType } from "./TemplatePickerModal";
import PreviewModal from "./PreviewModal";
import type {
  BuilderPlatform,
  BuilderElements,
  ClearPassElements,
  ClearPassCredentials,
  ISECredentials,
  CanvasState,
  CanvasRoleMappingState,
  CanvasEnforcementState,
  BuilderConditionExpr,
} from "../../api/builderApi";

// ---------------------------------------------------------------------------
// JSON export helper
// ---------------------------------------------------------------------------

function exportCanvasAsJson(state: CanvasState) {
  const payload = {
    service: {
      name: state.service.name,
      service_type: state.service.serviceType,
      description: state.service.description,
      match: state.service.match,
    },
    auth: state.auth,
    role_mapping_policy: {
      id: state.roleMappingPolicy.id,
      name: state.roleMappingPolicy.name,
      rules: state.roleMappingPolicy.rules,
      default_role_id: state.roleMappingPolicy.defaultRoleId,
      default_role_name: state.roleMappingPolicy.defaultRoleName,
    },
    enforcement_policy: {
      id: state.enforcementPolicy.id,
      name: state.enforcementPolicy.name,
      rules: state.enforcementPolicy.rules,
      default_profile_ids: state.enforcementPolicy.defaultProfileIds,
      default_profile_names: state.enforcementPolicy.defaultProfileNames,
    },
    roles: state.roles,
    enforcement_profiles: state.enforcementProfiles,
  };
  const json = JSON.stringify(payload, null, 2);
  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${state.service.name || "service"}-builder.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Template-to-canvas-state converters
// ---------------------------------------------------------------------------

// ClearPass REST API operator names → canonical op enum values
const CP_OP_MAP: Record<string, string> = {
  EQUALS: "equals",
  NOT_EQUALS: "not_equals",
  CONTAINS: "contains",
  NOT_CONTAINS: "not_contains",
  STARTS_WITH: "starts_with",
  ENDS_WITH: "ends_with",
  NOT_ENDS_WITH: "not_ends_with",
  REGEX_MATCH: "regex",
  IN: "in",
  MATCHES_ANY: "in",
  EXISTS: "exists",
  NOT_EXISTS: "not_exists",
  LESS_THAN: "less_than",
  GREATER_THAN: "greater_than",
  BELONGS_TO_GROUP: "belongs_to_group",
};

/**
 * Parse ClearPass REST API conditions into BuilderConditionExpr.
 *
 * ClearPass REST API format variants:
 *   { type: "Authorization:MSU-AD", name: "memberOf", oper: "CONTAINS", value: "..." }
 *   { type: "Authorization:MSU-AD", name: "memberOf", operator: "CONTAINS", value: "..." }
 * where `type` is the namespace and `name` is the attribute.
 * Some responses also use attr_name / attr_oper / attr_value field names.
 */
function parseClearPassConditions(
  rawConditions: Record<string, unknown>[] | undefined,
  combinerType: string | undefined,
): BuilderConditionExpr | null {
  if (!rawConditions || rawConditions.length === 0) return null;

  const conditions = rawConditions
    .map((c) => {
      // Namespace: "type" field; fall back to "namespace" or "attr_name" split
      const namespace = String(c.type ?? c.namespace ?? "");
      // Attribute: "name" field; fall back to "attribute" or "attr_name"
      const attribute = String(c.name ?? c.attribute ?? "");
      // Operator: "oper" (REST API) or "operator" (mirrors XML field name)
      const rawOp = String(c.oper ?? c.operator ?? c.attr_oper ?? "").toUpperCase();
      const op = CP_OP_MAP[rawOp] ?? (rawOp ? rawOp.toLowerCase() : "equals");
      // Value: "value" field; fall back to "attr_value"
      const value = String(c.value ?? c.attr_value ?? "");
      return { namespace, attribute, op, value };
    })
    .filter((c) => c.namespace || c.attribute);

  if (conditions.length === 0) return null;

  const combinator = String(combinerType ?? "AND").toUpperCase() === "OR" ? "or" : "and";
  return { combinator, conditions };
}

function rawPolicyToRoleMapping(raw: Record<string, unknown>, existingState: CanvasRoleMappingState): CanvasRoleMappingState {
  console.debug("[Builder] raw role-mapping policy from ClearPass API:", raw);
  const rawRules = (raw.rules as Record<string, unknown>[] | undefined) ?? [];
  const rules = rawRules.map((r, idx) => {
    // ClearPass REST API uses "condition" (singular array); some responses use "conditions" (plural)
    const condArr = (r.condition ?? r.conditions) as Record<string, unknown>[] | undefined;
    const condition = parseClearPassConditions(condArr, r.match_type as string | undefined);

    // ClearPass REST API: roles is [{id, name}]; fall back to Policy IR then.role_id
    const roles = (r.roles as Record<string, unknown>[] | undefined) ?? [];
    const role_id = String(roles[0]?.id ?? (r.then as Record<string, unknown> | undefined)?.role_id ?? "");
    const role_name = String(roles[0]?.name ?? (r.then as Record<string, unknown> | undefined)?.role_name ?? "");

    // stop_if_match is a boolean in the ClearPass REST API
    const on_match: "stop" | "continue" =
      r.stop_if_match === false
        ? "continue"
        : (((r.flow as Record<string, unknown> | undefined)?.on_match as "stop" | "continue") ?? "stop");

    return {
      id: String(r.id ?? uuidv4()),
      name: String(r.name ?? `Rule ${idx + 1}`),
      condition,
      role_action: { role_id, role_name },
      on_match,
    };
  });
  // ClearPass REST API: default_role is {id, name} or separate default_role_id
  const defaultRoleObj = raw.default_role as Record<string, unknown> | undefined;
  const defaultRoleId = String(defaultRoleObj?.id ?? raw.default_role_id ?? existingState.defaultRoleId);
  const defaultRoleName = String(defaultRoleObj?.name ?? raw.default_role_name ?? existingState.defaultRoleName);

  return {
    ...existingState,
    id: String(raw.id ?? existingState.id),
    name: String(raw.name ?? existingState.name),
    rules,
    defaultRoleId,
    defaultRoleName,
  };
}

function rawPolicyToEnforcement(
  raw: Record<string, unknown>,
  existingState: CanvasEnforcementState,
  knownProfiles?: { id: string; name: string }[],
): CanvasEnforcementState {
  console.debug("[Builder] raw enforcement policy from ClearPass API:", raw);
  console.debug("[Builder] enforcement policy keys:", Object.keys(raw));
  console.debug("[Builder] default_enforcement_profiles field:", raw.default_enforcement_profiles);
  console.debug("[Builder] default field:", raw.default);
  console.debug("[Builder] knownProfiles count:", knownProfiles?.length ?? 0);

  // Resolve profile names → IDs using the known profiles list from elements.
  function resolveProfileIds(names: string[]): string[] {
    if (!knownProfiles) return names; // use name as fallback ID
    return names.map((n) => {
      const found = knownProfiles.find((p) => p.name === n);
      if (!found) console.warn("[Builder] could not resolve profile name to ID:", n);
      return found ? found.id : n;
    });
  }

  const rawRules = (raw.rules as Record<string, unknown>[] | undefined) ?? [];
  const rules = rawRules.map((r, idx) => {
    const condArr = (r.condition ?? r.conditions) as Record<string, unknown>[] | undefined;
    const condition = parseClearPassConditions(condArr, r.match_type as string | undefined);

    // ClearPass REST API: enforcement_profile_names is string[]; fall back to Policy IR then.profile_names
    const profile_names: string[] =
      (r.enforcement_profile_names as string[] | undefined) ??
      ((r.then as Record<string, unknown> | undefined)?.profile_names as string[] | undefined) ??
      [];
    const profile_ids: string[] =
      (r.enforcement_profile_ids as string[] | undefined) ??
      ((r.then as Record<string, unknown> | undefined)?.profile_ids as string[] | undefined) ??
      resolveProfileIds(profile_names);

    const on_match: "stop" | "continue" =
      r.stop_if_match === false
        ? "continue"
        : (((r.flow as Record<string, unknown> | undefined)?.on_match as "stop" | "continue") ?? "stop");

    return {
      id: String(r.id ?? uuidv4()),
      name: String(r.name ?? `Rule ${idx + 1}`),
      condition,
      enforcement_action: { profile_ids, profile_names },
      on_match,
    };
  });

  // ClearPass REST API: default_enforcement_profile is a single string (e.g. "[Deny Access Profile]")
  // Some variants use the plural array form; handle both.
  const rawDefault = raw.default_enforcement_profile ?? raw.default_enforcement_profiles;
  const defaultProfileNames: string[] =
    typeof rawDefault === "string"
      ? [rawDefault]
      : (rawDefault as string[] | undefined) ??
        ((raw.default as Record<string, unknown> | undefined)?.profile_names as string[] | undefined) ??
        existingState.defaultProfileNames;
  const defaultProfileIds: string[] =
    ((raw.default as Record<string, unknown> | undefined)?.profile_ids as string[] | undefined) ??
    (raw.default_enforcement_profile_ids as string[] | undefined) ??
    resolveProfileIds(defaultProfileNames);

  console.debug("[Builder] resolved defaultProfileNames:", defaultProfileNames);
  console.debug("[Builder] resolved defaultProfileIds:", defaultProfileIds);

  return {
    ...existingState,
    id: String(raw.id ?? existingState.id),
    name: String(raw.name ?? existingState.name),
    rules,
    defaultProfileIds,
    defaultProfileNames,
  };
}

// ---------------------------------------------------------------------------
// Service template converter
// ---------------------------------------------------------------------------

/**
 * Parse a ClearPass REST API service object into a CanvasState.
 *
 * Defensively maps known field names; falls back gracefully on unknowns.
 * Role mapping and enforcement policies are pre-named but left rule-empty
 * so the user can drag those policies from the library to template them.
 */
function rawServiceToCanvasState(raw: Record<string, unknown>, elements: ClearPassElements): CanvasState {
  // Log the raw service data so the actual API shape is visible in DevTools → Console
  console.debug("[Builder] raw service from ClearPass API:", raw);

  const name = String(raw.name ?? "");

  // Service type: ClearPass REST API uses "type" field (e.g. "TACACS"); fall back to other field names
  const typeStr = String(raw.type ?? raw.template_type ?? raw.service_type ?? "").toUpperCase();
  const serviceType: "RADIUS" | "TACACS" = typeStr.includes("TACACS") ? "TACACS" : "RADIUS";

  // Match conditions: ClearPass REST API uses "rules_conditions"; fall back to other field names
  const rawConditions =
    (raw.rules_conditions as Record<string, unknown>[] | undefined) ??
    (raw.conditions as Record<string, unknown>[] | undefined) ??
    (raw.condition as Record<string, unknown>[] | undefined) ??
    (raw.match_conditions as Record<string, unknown>[] | undefined) ??
    [];
  // ClearPass REST API combinator: "rules_match_type" = "MATCHES_ANY" / "MATCHES_ALL"
  const matchType = String(raw.rules_match_type ?? raw.match_type ?? "AND");
  const match = parseClearPassConditions(rawConditions, matchType);

  // Auth methods: may be array of strings or array of objects
  function parseAuthItems(val: unknown): { id: string; name: string }[] {
    if (!Array.isArray(val)) return [];
    return val.map((item) => {
      if (typeof item === "string") return { id: item, name: item };
      const obj = item as Record<string, unknown>;
      const n = String(obj.name ?? obj.id ?? "");
      return { id: String(obj.id ?? n), name: n };
    }).filter((a) => a.name);
  }

  const methods = parseAuthItems(raw.authentication_methods ?? raw.auth_methods);
  const sources = parseAuthItems(raw.authentication_sources ?? raw.authorization_sources ?? raw.auth_sources);

  // Linked policy names (ClearPass may return name string or object)
  function extractPolicyName(val: unknown): string {
    if (typeof val === "string") return val;
    if (val && typeof val === "object") {
      const obj = val as Record<string, unknown>;
      return String(obj.name ?? obj.id ?? "");
    }
    return "";
  }

  const rmPolicyName = extractPolicyName(raw.role_mapping_policy ?? raw.role_mapping_policies) || `${name} Role Mapping`;
  // ClearPass REST API uses "enf_policy" for enforcement policy name
  const enfPolicyName = extractPolicyName(raw.enf_policy ?? raw.enforcement_policy ?? raw.authorization_policy) || `${name} Enforcement`;

  return {
    service: { name, serviceType, description: String(raw.description ?? ""), match },
    auth: { methods, sources },
    roleMappingPolicy: {
      id: uuidv4(),
      name: rmPolicyName,
      rules: [],
      defaultRoleId: "",
      defaultRoleName: "",
    },
    enforcementPolicy: {
      id: uuidv4(),
      name: enfPolicyName,
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
}

// ---------------------------------------------------------------------------
// BuilderView
// ---------------------------------------------------------------------------

export default function BuilderView() {
  const [platform, setPlatform] = useState<BuilderPlatform | null>(null);
  const [elements, setElements] = useState<BuilderElements | null>(null);
  const [creds, setCreds] = useState<ClearPassCredentials | null>(null);
  const [libCollapsed, setLibCollapsed] = useState(false);

  const [canvasState, setCanvasState] = useState<CanvasState | null>(null);
  const [selectedNode, setSelectedNode] = useState<SelectedNodeType>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [wizardInitialName, setWizardInitialName] = useState<string | undefined>(undefined);
  const [wizardInitialType, setWizardInitialType] = useState<"RADIUS" | "TACACS" | undefined>(undefined);
  const [showPreview, setShowPreview] = useState(false);

  // Template picker state
  const [templatePicker, setTemplatePicker] = useState<{
    policyName: string;
    policyId: string;
    policyType: TemplatePolicyType;
  } | null>(null);

  function handleConnect(p: BuilderPlatform, elems: BuilderElements, connCreds: ClearPassCredentials | ISECredentials) {
    setPlatform(p);
    setElements(elems);
    // Only store ClearPass credentials (identified by presence of clientId)
    if ("clientId" in connCreds) {
      setCreds(connCreds as ClearPassCredentials);
    }
  }

  function handleDisconnect() {
    setPlatform(null);
    setElements(null);
    setCreds(null);
  }

  function handleCanvasDrop(sectionKey: string, item: Record<string, unknown>) {
    if (!creds) return;

    const itemId = String(item.id ?? item.name ?? "");
    const itemName = String(item.name ?? "(unnamed)");

    // Services can start a new canvas even when one doesn't exist yet
    if (sectionKey === "services") {
      setTemplatePicker({ policyName: itemName, policyId: itemId, policyType: "service" });
      return;
    }

    if (!canvasState) return;

    if (sectionKey === "role_mapping_policies") {
      setTemplatePicker({ policyName: itemName, policyId: itemId, policyType: "role_mapping" });
    } else if (sectionKey === "enforcement_policies") {
      setTemplatePicker({ policyName: itemName, policyId: itemId, policyType: "enforcement" });
    } else if (sectionKey === "auth_methods") {
      // Add to Auth node methods (deduplicate)
      if (!canvasState.auth.methods.some((m) => m.id === itemId)) {
        setCanvasState({
          ...canvasState,
          auth: { ...canvasState.auth, methods: [...canvasState.auth.methods, { id: itemId, name: itemName }] },
        });
      }
    } else if (sectionKey === "auth_sources") {
      if (!canvasState.auth.sources.some((s) => s.id === itemId)) {
        setCanvasState({
          ...canvasState,
          auth: { ...canvasState.auth, sources: [...canvasState.auth.sources, { id: itemId, name: itemName }] },
        });
      }
    }
    // Other section drops are silently ignored for MVP
  }

  function handleTemplateUse(rawData: Record<string, unknown>) {
    if (!templatePicker) return;

    if (templatePicker.policyType === "service") {
      const elems = cpElements ?? {
        services: [], roles: [], enforcement_profiles: [],
        enforcement_policies: [], role_mapping_policies: [],
        auth_methods: [], auth_sources: [], warnings: [],
      };
      let state = rawServiceToCanvasState(rawData, elems);

      // Apply linked policies fetched by TemplatePickerModal
      const rmPolicy = rawData._rm_policy as Record<string, unknown> | undefined;
      const enfPolicy = rawData._enf_policy as Record<string, unknown> | undefined;
      if (rmPolicy) {
        state = { ...state, roleMappingPolicy: rawPolicyToRoleMapping(rmPolicy, state.roleMappingPolicy) };
      }
      if (enfPolicy) {
        state = { ...state, enforcementPolicy: rawPolicyToEnforcement(enfPolicy, state.enforcementPolicy, state.enforcementProfiles) };
      }

      setCanvasState(state);
      setTemplatePicker(null);
      return;
    }

    if (!canvasState) return;
    if (templatePicker.policyType === "role_mapping") {
      setCanvasState({
        ...canvasState,
        roleMappingPolicy: rawPolicyToRoleMapping(rawData, canvasState.roleMappingPolicy),
      });
    } else {
      setCanvasState({
        ...canvasState,
        enforcementPolicy: rawPolicyToEnforcement(rawData, canvasState.enforcementPolicy, canvasState.enforcementProfiles),
      });
    }
    setTemplatePicker(null);
  }

  function handleTemplateBlank() {
    if (!templatePicker) return;
    const { policyName, policyId, policyType } = templatePicker;

    if (policyType === "service") {
      // Parse service type from the item in the elements list (if available)
      const serviceItem = cpElements?.services.find(
        (s) => String(s.id ?? s.name ?? "") === policyId
      );
      const typeStr = String((serviceItem as Record<string, unknown> | undefined)?.template_type ?? "").toUpperCase();
      const serviceType: "RADIUS" | "TACACS" = typeStr.includes("TACACS") ? "TACACS" : "RADIUS";
      setTemplatePicker(null);
      setWizardInitialName(policyName);
      setWizardInitialType(serviceType);
      setShowWizard(true);
      return;
    }

    if (!canvasState) return;
    if (policyType === "role_mapping") {
      setCanvasState({
        ...canvasState,
        roleMappingPolicy: {
          ...canvasState.roleMappingPolicy,
          id: policyId,
          name: policyName,
          rules: [],
        },
      });
    } else {
      setCanvasState({
        ...canvasState,
        enforcementPolicy: {
          ...canvasState.enforcementPolicy,
          id: policyId,
          name: policyName,
          rules: [],
        },
      });
    }
    setTemplatePicker(null);
  }

  const cpElements = platform === "clearpass" ? (elements as ClearPassElements) : null;

  return (
    <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
      {/* Left: Connection + Library */}
      <div style={{
        width: libCollapsed ? 40 : 280,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        borderRight: "1px solid #e5e7eb",
        background: "#fff",
        transition: "width 0.15s ease",
        overflow: "hidden",
      }}>
        {libCollapsed ? (
          <button
            onClick={() => setLibCollapsed(false)}
            title="Expand library"
            style={{
              flex: 1,
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "#9ca3af",
              fontSize: 16,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            ›
          </button>
        ) : (
          <>
            {/* Collapse toggle */}
            <div style={{ display: "flex", justifyContent: "flex-end", padding: "4px 6px 0" }}>
              <button
                onClick={() => setLibCollapsed(true)}
                title="Collapse library"
                style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", fontSize: 14, padding: "2px 4px" }}
              >
                ‹
              </button>
            </div>

            <div style={{ overflowY: "auto", flex: 1 }}>
              <ConnectionPanel
                onConnect={(p, elems, connCreds) => handleConnect(p, elems, connCreds)}
                onDisconnect={handleDisconnect}
              />

              {elements && platform && (
                <div style={{ padding: "0 12px 16px" }}>
                  <ElementsLibrary
                    elements={elements}
                    platform={platform}
                    canDrag={(sectionKey) => sectionKey === "services" || !!canvasState}
                  />
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Center: Canvas */}
      <BuilderCanvas
        canvasState={canvasState}
        selectedNode={selectedNode}
        onNodeSelect={setSelectedNode}
        onNewService={() => setShowWizard(true)}
        onPreview={() => canvasState && setShowPreview(true)}
        onExport={() => canvasState && exportCanvasAsJson(canvasState)}
        onDrop={handleCanvasDrop}
        creds={creds}
      />

      {/* Right: Side panel (only when canvas has content) */}
      {canvasState && (
        <BuilderSidePanel
          selectedNode={selectedNode}
          canvasState={canvasState}
          onChange={setCanvasState}
          creds={creds}
        />
      )}

      {/* Wizard modal */}
      {showWizard && (
        <NewServiceWizard
          elements={cpElements ?? {
            services: [], roles: [], enforcement_profiles: [],
            enforcement_policies: [], role_mapping_policies: [],
            auth_methods: [], auth_sources: [], warnings: [],
          }}
          creds={creds}
          initialName={wizardInitialName}
          initialServiceType={wizardInitialType}
          onComplete={(state) => {
            setCanvasState(state);
            setShowWizard(false);
            setWizardInitialName(undefined);
            setWizardInitialType(undefined);
          }}
          onCancel={() => {
            setShowWizard(false);
            setWizardInitialName(undefined);
            setWizardInitialType(undefined);
          }}
        />
      )}

      {/* Template picker modal */}
      {templatePicker && creds && (
        <TemplatePickerModal
          policyName={templatePicker.policyName}
          policyId={templatePicker.policyId}
          policyType={templatePicker.policyType}
          creds={creds}
          elements={cpElements ?? undefined}
          onTemplate={handleTemplateUse}
          onBlank={handleTemplateBlank}
          onCancel={() => setTemplatePicker(null)}
        />
      )}

      {/* Preview modal */}
      {showPreview && canvasState && (
        <PreviewModal
          canvasState={canvasState}
          onClose={() => setShowPreview(false)}
        />
      )}
    </div>
  );
}
