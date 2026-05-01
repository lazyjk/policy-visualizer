/**
 * Fetch wrappers for the Policy Builder backend proxy endpoints.
 * All requests POST JSON credentials to /api/builder/*; the backend
 * proxies them to the live ClearPass or ISE instance.
 */

const BASE = "/api/builder";

export type BuilderPlatform = "clearpass" | "ise";

// ---------------------------------------------------------------------------
// Credential types
// ---------------------------------------------------------------------------

export interface ClearPassCredentials {
  serverUrl: string;
  clientId: string;
  clientSecret: string;
  verifySsl: boolean;
}

export interface ISECredentials {
  serverUrl: string;
  username: string;
  password: string;
  verifySsl: boolean;
}

// ---------------------------------------------------------------------------
// Response types
// ---------------------------------------------------------------------------

export interface ConnectResponse {
  success: boolean;
  platform: string;
  version: string | null;
  error: string | null;
}

// Typed shapes emitted by the Pydantic normalization layer (clearpass_api_schemas.py).
// These match the canonical model_dump() output of each CP* model.

export interface CPCondition {
  namespace: string;    // normalized from: type | namespace
  attribute: string;    // normalized from: name | attribute | attr_name
  operator: string;     // normalized from: oper | operator | attr_oper  (uppercase)
  value: string;        // normalized from: value | attr_value
}

export interface CPLinkedPolicy {
  id: string;
  name: string;
}

export interface CPServiceListItem {
  id: string;
  name: string;
  service_type: string;  // normalized from: type | template_type | service_type
}

export interface CPRoleItem {
  id: string;
  name: string;
}

export interface CPEnforcementProfileItem {
  id: string;
  name: string;
  profile_type: string;
}

export interface CPEnforcementPolicyListItem {
  id: string;
  name: string;
}

export interface CPRoleMappingListItem {
  id: string;
  name: string;
}

export interface CPAuthMethodItem {
  id: string;
  name: string;
}

export interface CPAuthSourceItem {
  id: string;
  name: string;
}

export interface CPRoleMappingRule {
  id: string;
  name: string;
  conditions: CPCondition[];  // normalized from: condition | conditions
  match_type: string;
  roles: { id: string; name: string }[];
  stop_if_match: boolean;     // normalized from: stop_if_match | flow.on_match
}

export interface CPRoleMappingPolicy {
  id: string;
  name: string;
  rules: CPRoleMappingRule[];
  default_role: { id: string; name: string };
}

export interface CPEnforcementPolicyRule {
  id: string;
  name: string;
  conditions: CPCondition[];
  match_type: string;
  enforcement_profile_names: string[];  // normalized from: enforcement_profile_names | then.profile_names
  enforcement_profile_ids: string[];    // normalized from: enforcement_profile_ids | then.profile_ids
  stop_if_match: boolean;
}

export interface CPEnforcementPolicy {
  id: string;
  name: string;
  rules: CPEnforcementPolicyRule[];
  default_enforcement_profile_names: string[];  // normalized from all default field variants
  default_enforcement_profile_ids: string[];
}

export interface CPService {
  id: string;
  name: string;
  service_type: string;                   // normalized from: type | template_type | service_type
  description: string;
  rules_conditions: CPCondition[];        // normalized from: rules_conditions | conditions | condition | match_conditions
  rules_match_type: string;               // normalized from: rules_match_type | match_type
  authentication_methods: { id: string; name: string }[];
  authentication_sources: { id: string; name: string }[];
  role_mapping_policy: CPLinkedPolicy;
  enf_policy: CPLinkedPolicy;
}

export interface ClearPassElements {
  services: CPServiceListItem[];
  roles: CPRoleItem[];
  enforcement_profiles: CPEnforcementProfileItem[];
  enforcement_policies: CPEnforcementPolicyListItem[];
  role_mapping_policies: CPRoleMappingListItem[];
  auth_methods: CPAuthMethodItem[];
  auth_sources: CPAuthSourceItem[];
  warnings: string[];
}

export interface ISEElements {
  radius_policy_sets: Record<string, unknown>[];
  tacacs_policy_sets: Record<string, unknown>[];
  profiles: Record<string, unknown>[];
  identity_stores: Record<string, unknown>[];
  warnings: string[];
}

export type BuilderElements = ClearPassElements | ISEElements;

// ---------------------------------------------------------------------------
// Internal helper
// ---------------------------------------------------------------------------

async function post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// ClearPass
// ---------------------------------------------------------------------------

export async function connectClearPass(
  creds: ClearPassCredentials
): Promise<ConnectResponse> {
  return post<ConnectResponse>("/clearpass/connect", {
    server_url: creds.serverUrl,
    client_id: creds.clientId,
    client_secret: creds.clientSecret,
    verify_ssl: creds.verifySsl,
  });
}

export async function fetchClearPassElements(
  creds: ClearPassCredentials
): Promise<ClearPassElements> {
  return post<ClearPassElements>("/clearpass/elements", {
    server_url: creds.serverUrl,
    client_id: creds.clientId,
    client_secret: creds.clientSecret,
    verify_ssl: creds.verifySsl,
  });
}

// ---------------------------------------------------------------------------
// ISE
// ---------------------------------------------------------------------------

export async function connectISE(
  creds: ISECredentials
): Promise<ConnectResponse> {
  return post<ConnectResponse>("/ise/connect", {
    server_url: creds.serverUrl,
    username: creds.username,
    password: creds.password,
    verify_ssl: creds.verifySsl,
  });
}

export async function fetchISEElements(
  creds: ISECredentials
): Promise<ISEElements> {
  return post<ISEElements>("/ise/elements", {
    server_url: creds.serverUrl,
    username: creds.username,
    password: creds.password,
    verify_ssl: creds.verifySsl,
  });
}

// ---------------------------------------------------------------------------
// Canvas state types
// ---------------------------------------------------------------------------

/** A single leaf predicate in the condition builder. */
export interface BuilderCondition {
  namespace: string;
  attribute: string;
  op: string;   // canonical Op value, e.g. "equals"
  value: string;
}

/** Flat AND/OR list of predicates (MVP depth = 1). */
export interface BuilderConditionExpr {
  combinator: "and" | "or";
  conditions: BuilderCondition[];
}

export interface BuilderAuthItem {
  id: string;
  name: string;
}

export interface BuilderRoleMappingAction {
  role_id: string;
  role_name: string;
}

export interface BuilderEnforcementAction {
  profile_ids: string[];
  profile_names: string[];
}

export interface BuilderRule {
  id: string;
  name: string;
  condition: BuilderConditionExpr | null;   // null = match-all
  role_action?: BuilderRoleMappingAction;
  enforcement_action?: BuilderEnforcementAction;
  on_match: "stop" | "continue";
}

export interface CanvasServiceState {
  name: string;
  serviceType: "RADIUS" | "TACACS";
  description: string;
  match: BuilderConditionExpr | null;
}

export interface CanvasAuthState {
  methods: BuilderAuthItem[];
  sources: BuilderAuthItem[];
}

export interface CanvasRoleMappingState {
  id?: string;
  name: string;
  rules: BuilderRule[];
  defaultRoleId: string;
  defaultRoleName: string;
}

export interface CanvasEnforcementState {
  id?: string;
  name: string;
  rules: BuilderRule[];
  defaultProfileIds: string[];
  defaultProfileNames: string[];
}

export interface CanvasRoleItem {
  id: string;
  name: string;
}

export interface CanvasProfileItem {
  id: string;
  name: string;
  profile_type: string;
}

/** Full canvas state — the source of truth for the builder canvas. */
export interface CanvasState {
  service: CanvasServiceState;
  auth: CanvasAuthState;
  roleMappingPolicy: CanvasRoleMappingState;
  enforcementPolicy: CanvasEnforcementState;
  roles: CanvasRoleItem[];
  enforcementProfiles: CanvasProfileItem[];
}

// ---------------------------------------------------------------------------
// Attribute dictionary types
// ---------------------------------------------------------------------------

export interface AttributeDict {
  namespaces: Record<string, string[]>;
  warnings: string[];
}

export interface PolicyDetailResponse {
  policy: CPRoleMappingPolicy | CPEnforcementPolicy;
  warnings: string[];
}

export interface ServiceDetailResponse {
  service: CPService;
  warnings: string[];
}

// ---------------------------------------------------------------------------
// ClearPass — attributes + policy detail
// ---------------------------------------------------------------------------

export async function fetchClearPassAttributes(
  creds: ClearPassCredentials
): Promise<AttributeDict> {
  return post<AttributeDict>("/clearpass/attributes", {
    server_url: creds.serverUrl,
    client_id: creds.clientId,
    client_secret: creds.clientSecret,
    verify_ssl: creds.verifySsl,
  });
}

export async function fetchClearPassServiceDetail(
  creds: ClearPassCredentials,
  serviceId: string
): Promise<ServiceDetailResponse> {
  return post<ServiceDetailResponse>("/clearpass/service-detail", {
    server_url: creds.serverUrl,
    client_id: creds.clientId,
    client_secret: creds.clientSecret,
    verify_ssl: creds.verifySsl,
    service_id: serviceId,
  });
}

export async function fetchClearPassPolicyDetail(
  creds: ClearPassCredentials,
  policyType: "role_mapping" | "enforcement",
  policyId: string
): Promise<PolicyDetailResponse> {
  return post<PolicyDetailResponse>("/clearpass/policy-detail", {
    server_url: creds.serverUrl,
    client_id: creds.clientId,
    client_secret: creds.clientSecret,
    verify_ssl: creds.verifySsl,
    policy_type: policyType,
    policy_id: policyId,
  });
}

// ---------------------------------------------------------------------------
// Preview from builder IR
// ---------------------------------------------------------------------------

import type { FlowIR } from "../api";

function _canvasStateToPayload(state: CanvasState): Record<string, unknown> {
  const condExprToJson = (expr: BuilderConditionExpr | null) =>
    expr
      ? { combinator: expr.combinator, conditions: expr.conditions }
      : null;

  const ruleToJson = (r: BuilderRule) => ({
    id: r.id,
    name: r.name,
    condition: condExprToJson(r.condition),
    role_action: r.role_action ?? null,
    enforcement_action: r.enforcement_action ?? null,
    on_match: r.on_match,
  });

  return {
    service: {
      name: state.service.name,
      service_type: state.service.serviceType,
      description: state.service.description,
      match: condExprToJson(state.service.match),
    },
    auth: {
      methods: state.auth.methods,
      sources: state.auth.sources,
    },
    role_mapping_policy: {
      id: state.roleMappingPolicy.id ?? "",
      name: state.roleMappingPolicy.name,
      rules: state.roleMappingPolicy.rules.map(ruleToJson),
      default_role_id: state.roleMappingPolicy.defaultRoleId,
      default_role_name: state.roleMappingPolicy.defaultRoleName,
    },
    enforcement_policy: {
      id: state.enforcementPolicy.id ?? "",
      name: state.enforcementPolicy.name,
      rules: state.enforcementPolicy.rules.map(ruleToJson),
      default_profile_ids: state.enforcementPolicy.defaultProfileIds,
      default_profile_names: state.enforcementPolicy.defaultProfileNames,
    },
    roles: state.roles,
    enforcement_profiles: state.enforcementProfiles,
  };
}

export async function previewFromIR(state: CanvasState): Promise<FlowIR> {
  const payload = _canvasStateToPayload(state);
  const res = await fetch("/api/flow/from-ir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? res.statusText);
  }
  return res.json() as Promise<FlowIR>;
}
