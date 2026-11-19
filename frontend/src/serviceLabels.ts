/**
 * Display helpers for ClearPass service metadata shared by the service picker
 * and the Policy Inspector.
 */

// ClearPass <ServiceTemplate> / tips_service.service_template → friendly name.
// Unknown values fall back to the raw template string.
const TEMPLATE_LABELS: Record<string, string> = {
  IBNS_WIRELESS: "802.1X Wireless",
  IBNS_WIRED: "802.1X Wired",
  IBNS_WIRED_IDENTITY: "802.1X Wired (Identity Only)",
  ARUBA_IBNS_WIRELESS: "Aruba 802.1X Wireless",
  RADIUS_ENFORCEMENT: "RADIUS Enforcement",
  RADIUS_PROXY: "RADIUS Proxy",
  TACACS_ENFORCEMENT: "TACACS+ Enforcement",
  AVENDA_WEB_AUTH: "Web-based Auth",
  AVENDA_APP_AUTH: "Application Auth",
  CPPM_APP_AUTZ: "Application Authorization",
  MAC_AUTH: "MAC Authentication",
  MAC_AUTH_BYPASS: "MAC Authentication",
  RADIUS_AUTZ: "RADIUS Authorization",
  CISCO_WEB_AUTH: "Cisco Web Auth",
};

export function templateLabel(template: string): string {
  if (!template) return "";
  return TEMPLATE_LABELS[template] ?? template;
}
