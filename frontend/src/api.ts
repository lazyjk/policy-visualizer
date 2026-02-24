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

export interface FlowEdge {
  from_id: string;
  to_id: string;
  label: string;
}

export interface FlowIR {
  service_id: string;
  service_name: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface ServiceSummary {
  id: string;
  name: string;
  description: string;
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

export async function fetchFlow(file: File, serviceName?: string): Promise<FlowIR> {
  const form = new FormData();
  form.append("file", file);
  const url = serviceName
    ? `${BASE}/flow?service=${encodeURIComponent(serviceName)}`
    : `${BASE}/flow`;
  const res = await fetch(url, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.json();
}
