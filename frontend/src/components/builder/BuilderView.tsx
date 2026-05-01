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
  CPService,
  CPRoleMappingPolicy,
  CPEnforcementPolicy,
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
 * Convert a normalized CPCondition[] (from the backend schema layer) into a
 * BuilderConditionExpr.  Field names are already canonical — no fallbacks needed.
 */
function parseClearPassConditions(
  conditions: { namespace: string; attribute: string; operator: string; value: string }[],
  matchType: string | undefined,
): BuilderConditionExpr | null {
  const parsed = conditions
    .map((c) => {
      const rawOp = c.operator.toUpperCase();
      const op = CP_OP_MAP[rawOp] ?? (rawOp ? rawOp.toLowerCase() : "equals");
      return { namespace: c.namespace, attribute: c.attribute, op, value: c.value };
    })
    .filter((c) => c.namespace || c.attribute);

  if (parsed.length === 0) return null;

  const combinator =
    String(matchType ?? "AND").toUpperCase().includes("ANY") ||
    String(matchType ?? "AND").toUpperCase() === "OR"
      ? "or"
      : "and";
  return { combinator, conditions: parsed };
}

function rawPolicyToRoleMapping(raw: CPRoleMappingPolicy, existingState: CanvasRoleMappingState): CanvasRoleMappingState {
  const rules = raw.rules.map((r, idx) => {
    const condition = parseClearPassConditions(r.conditions, r.match_type);
    const role_id = r.roles[0]?.id ?? "";
    const role_name = r.roles[0]?.name ?? "";
    const on_match: "stop" | "continue" = r.stop_if_match === false ? "continue" : "stop";
    return {
      id: r.id || uuidv4(),
      name: r.name || `Rule ${idx + 1}`,
      condition,
      role_action: { role_id, role_name },
      on_match,
    };
  });

  return {
    ...existingState,
    id: raw.id || existingState.id,
    name: raw.name || existingState.name,
    rules,
    defaultRoleId: raw.default_role.id || existingState.defaultRoleId,
    defaultRoleName: raw.default_role.name || existingState.defaultRoleName,
  };
}

function rawPolicyToEnforcement(
  raw: CPEnforcementPolicy,
  existingState: CanvasEnforcementState,
  knownProfiles?: { id: string; name: string }[],
): CanvasEnforcementState {
  // Resolve profile names → IDs using the known profiles list from elements.
  function resolveProfileIds(names: string[]): string[] {
    if (!knownProfiles) return names; // use name as fallback ID
    return names.map((n) => {
      const found = knownProfiles.find((p) => p.name === n);
      return found ? found.id : n;
    });
  }

  const rules = raw.rules.map((r, idx) => {
    const condition = parseClearPassConditions(r.conditions, r.match_type);
    const profile_names = r.enforcement_profile_names;
    const profile_ids =
      r.enforcement_profile_ids.length > 0
        ? r.enforcement_profile_ids
        : resolveProfileIds(profile_names);
    const on_match: "stop" | "continue" = r.stop_if_match === false ? "continue" : "stop";
    return {
      id: r.id || uuidv4(),
      name: r.name || `Rule ${idx + 1}`,
      condition,
      enforcement_action: { profile_ids, profile_names },
      on_match,
    };
  });

  const defaultProfileNames =
    raw.default_enforcement_profile_names.length > 0
      ? raw.default_enforcement_profile_names
      : existingState.defaultProfileNames;
  const defaultProfileIds =
    raw.default_enforcement_profile_ids.length > 0
      ? raw.default_enforcement_profile_ids
      : resolveProfileIds(defaultProfileNames);

  return {
    ...existingState,
    id: raw.id || existingState.id,
    name: raw.name || existingState.name,
    rules,
    defaultProfileIds,
    defaultProfileNames,
  };
}

// ---------------------------------------------------------------------------
// Service template converter
// ---------------------------------------------------------------------------

/**
 * Convert a normalized CPService (from the backend schema layer) into a CanvasState.
 * Field names are already canonical — no fallbacks needed.
 */
function rawServiceToCanvasState(raw: CPService, elements: ClearPassElements): CanvasState {
  const serviceType: "RADIUS" | "TACACS" =
    raw.service_type.toUpperCase().includes("TACACS") ? "TACACS" : "RADIUS";
  const match = parseClearPassConditions(raw.rules_conditions, raw.rules_match_type);
  const rmPolicyName = raw.role_mapping_policy.name || `${raw.name} Role Mapping`;
  const enfPolicyName = raw.enf_policy.name || `${raw.name} Enforcement`;

  return {
    service: { name: raw.name, serviceType, description: raw.description, match },
    auth: {
      methods: raw.authentication_methods.filter((m) => m.name),
      sources: raw.authentication_sources.filter((s) => s.name),
    },
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
      id: r.id || uuidv4(),
      name: r.name || "(unnamed)",
    })),
    enforcementProfiles: elements.enforcement_profiles.map((p) => ({
      id: p.id || uuidv4(),
      name: p.name || "(unnamed)",
      profile_type: p.profile_type,
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

  function handleTemplateUse(rawData: unknown) {
    if (!templatePicker) return;

    if (templatePicker.policyType === "service") {
      const elems = cpElements ?? {
        services: [], roles: [], enforcement_profiles: [],
        enforcement_policies: [], role_mapping_policies: [],
        auth_methods: [], auth_sources: [], warnings: [],
      };
      const rawDataObj = rawData as Record<string, unknown>;
      let state = rawServiceToCanvasState(rawDataObj as unknown as CPService, elems);

      // Apply linked policies fetched by TemplatePickerModal
      const rmPolicy = rawDataObj._rm_policy as CPRoleMappingPolicy | undefined;
      const enfPolicy = rawDataObj._enf_policy as CPEnforcementPolicy | undefined;
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
        roleMappingPolicy: rawPolicyToRoleMapping(rawData as unknown as CPRoleMappingPolicy, canvasState.roleMappingPolicy),
      });
    } else {
      setCanvasState({
        ...canvasState,
        enforcementPolicy: rawPolicyToEnforcement(rawData as unknown as CPEnforcementPolicy, canvasState.enforcementPolicy, canvasState.enforcementProfiles),
      });
    }
    setTemplatePicker(null);
  }

  function handleTemplateBlank() {
    if (!templatePicker) return;
    const { policyName, policyId, policyType } = templatePicker;

    if (policyType === "service") {
      // Parse service type from the item in the elements list (if available)
      const serviceItem = cpElements?.services.find((s) => (s.id || s.name) === policyId);
      const serviceType: "RADIUS" | "TACACS" =
        serviceItem?.service_type.toUpperCase().includes("TACACS") ? "TACACS" : "RADIUS";
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
