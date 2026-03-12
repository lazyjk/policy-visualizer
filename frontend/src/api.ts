/**
 * Thin fetch() wrappers for the FastAPI backend.
 */

export interface FlowNode {
  id: string;
  type: string;
  label: string;
  sub_label: string;
  trace_rule_id: string;
  rank_group: string;
}

export type FlowEdgeLabel = "" | "YES" | "NO" | "FAIL" | "PASS" | "CONTINUE";

export interface FlowEdge {
  from_id: string;
  to_id: string;
  label: FlowEdgeLabel;
  reason: string;
}

export interface RuleDetail {
  rule_id: string;
  node_trace_id: string;
  index: number;
  name: string;
  condition_text: string;
  action_text: string;
  on_match: string;
  linked_names: string[];
}

export interface ServiceContext {
  service_name: string;
  service_type: string;
  description: string;
  auth_method_names: string[];
  auth_source_names: string[];
  condition_text: string;
}

export interface PolicyDetails {
  service_context: ServiceContext;
  authen_rules: RuleDetail[];
  role_mapping_rules: RuleDetail[];
  enforcement_rules: RuleDetail[];
  warnings: string[];
  rule_index: Record<string, RuleDetail>;
}

export interface FlowIR {
  service_id: string;
  service_name: string;
  service_type: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
  warnings: string[];
  details?: PolicyDetails;
}

export interface ServiceSummary {
  id: string;
  name: string;
  description: string;
  service_type: string;
}

export interface ServiceListResponse {
  services: ServiceSummary[];
}

const BASE = "/api";

export async function fetchServices(file: File): Promise<ServiceListResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/services`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.json();
}

export async function fetchFlow(file: File, serviceId?: string): Promise<FlowIR> {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ include_details: "true" });
  if (serviceId) params.set("service", serviceId);
  const res = await fetch(`${BASE}/flow?${params}`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.json();
}
