/**
 * Display helpers for ClearPass service metadata shared by the service picker
 * and the Policy Inspector.
 */

// ClearPass <ServiceTemplate> / tips_service.service_template → friendly name.
// Unknown values fall back to the raw template string.
const TEMPLATE_LABELS: Record<string, string> = {
  IBNS_WIRELESS: "802.1X Wireless",
  IBNS_WIRED: "802.1X Wired",
  RADIUS_ENFORCEMENT: "RADIUS Enforcement",
  RADIUS_PROXY: "RADIUS Proxy",
  TACACS_ENFORCEMENT: "TACACS+ Enforcement",
  AVENDA_WEB_AUTH: "Web-based Auth",
  AVENDA_APP_AUTH: "Application Auth",
  CPPM_APP_AUTZ: "Application Authorization",
  MAC_AUTH: "MAC Authentication",
};

export function templateLabel(template: string): string {
  if (!template) return "";
  return TEMPLATE_LABELS[template] ?? template;
}

/** "--------Wireless Services--------" → "Wireless Services". */
export function categoryLabel(name: string): string {
  return name.replace(/^[\s-]+|[\s-]+$/g, "") || name;
}
