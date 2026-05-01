/**
 * TemplatePickerModal — shown when a policy is dragged from the library.
 *
 * Asks: "Use [policy name] as template?" or "Start blank?"
 * If template is chosen, fetches full policy detail from ClearPass and
 * calls onTemplate with the raw policy data.
 */
import { useState } from "react";
import type { ClearPassCredentials, ClearPassElements, CPRoleMappingPolicy, CPEnforcementPolicy } from "../../api/builderApi";
import { fetchClearPassPolicyDetail, fetchClearPassServiceDetail } from "../../api/builderApi";

export type TemplatePolicyType = "role_mapping" | "enforcement" | "service";

interface Props {
  policyName: string;
  policyId: string;
  policyType: TemplatePolicyType;
  creds: ClearPassCredentials;
  /** ClearPass elements — used to resolve policy names to IDs when the API returns name strings */
  elements?: ClearPassElements;
  onTemplate: (rawPolicy: unknown) => void;
  onBlank: () => void;
  onCancel: () => void;
}

export default function TemplatePickerModal({
  policyName,
  policyId,
  policyType,
  creds,
  elements,
  onTemplate,
  onBlank,
  onCancel,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUseTemplate() {
    setLoading(true);
    setError(null);
    try {
      if (policyType === "service") {
        const result = await fetchClearPassServiceDetail(creds, policyId);
        const raw = result.service;

        // Resolve a policy name to its ID by looking it up in the elements list.
        function resolveByName(name: string, list?: { id: string; name: string }[]): string | null {
          if (!name || !list) return null;
          return list.find((e) => e.name === name)?.id ?? null;
        }

        const rmPolicies = elements?.role_mapping_policies;
        const enfPolicies = elements?.enforcement_policies;

        // raw.role_mapping_policy and raw.enf_policy are canonical CPLinkedPolicy {id, name}
        const rmId = raw.role_mapping_policy.id || resolveByName(raw.role_mapping_policy.name, rmPolicies) || null;
        const enfId = raw.enf_policy.id || resolveByName(raw.enf_policy.name, enfPolicies) || null;

        // Fetch linked policies in parallel; soft-fail on error
        const [rmResult, enfResult] = await Promise.allSettled([
          rmId ? fetchClearPassPolicyDetail(creds, "role_mapping", rmId) : Promise.resolve(null),
          enfId ? fetchClearPassPolicyDetail(creds, "enforcement", enfId) : Promise.resolve(null),
        ]);

        const enriched: { _rm_policy?: CPRoleMappingPolicy; _enf_policy?: CPEnforcementPolicy } & typeof raw = { ...raw };
        if (rmResult.status === "fulfilled" && rmResult.value) {
          enriched._rm_policy = rmResult.value.policy as CPRoleMappingPolicy;
        }
        if (enfResult.status === "fulfilled" && enfResult.value) {
          enriched._enf_policy = enfResult.value.policy as CPEnforcementPolicy;
        }

        onTemplate(enriched);
      } else {
        const result = await fetchClearPassPolicyDetail(creds, policyType, policyId);
        onTemplate(result.policy);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const isService = policyType === "service";
  const templateButtonLabel = isService
    ? `Load "${policyName}" as starting point`
    : `Use "${policyName}" as template`;
  const templateButtonSubLabel = isService
    ? "Pre-populate with the service's configuration from ClearPass"
    : "Pre-populate with existing rules from ClearPass";
  const blankButtonLabel = isService ? "Start blank service" : "Start blank";
  const blankButtonSubLabel = isService
    ? "Create a new empty service with the same name"
    : "Create a new empty policy with the same name";

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.4)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 1100,
    }}>
      <div style={{
        background: "#fff",
        borderRadius: 10,
        width: 400,
        padding: 24,
        boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
        fontFamily: "Helvetica, Arial, sans-serif",
      }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: "#111827", marginBottom: 8 }}>
          {isService ? "Load service" : "Load policy"}
        </div>
        <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 20 }}>
          You dropped <strong style={{ color: "#111827" }}>{policyName}</strong>.
          {isService
            ? " Would you like to load it as your starting point or start with a blank service?"
            : " Would you like to use it as a template (pre-populated with its current rules) or start with a blank policy?"}
        </div>

        {error && (
          <div style={{
            background: "#fef2f2",
            border: "1px solid #fca5a5",
            borderRadius: 5,
            padding: "8px 12px",
            fontSize: 12,
            color: "#dc2626",
            marginBottom: 16,
          }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <button
            onClick={handleUseTemplate}
            disabled={loading}
            style={{
              padding: "10px 16px",
              background: loading ? "#93c5fd" : "#3b82f6",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 600,
              cursor: loading ? "default" : "pointer",
              fontFamily: "Helvetica, Arial, sans-serif",
              textAlign: "left",
            }}
          >
            {loading ? "Loading…" : templateButtonLabel}
            {!loading && (
              <span style={{ display: "block", fontSize: 11, fontWeight: 400, opacity: 0.85, marginTop: 2 }}>
                {templateButtonSubLabel}
              </span>
            )}
          </button>

          <button
            onClick={onBlank}
            disabled={loading}
            style={{
              padding: "10px 16px",
              background: "#f9fafb",
              color: "#374151",
              border: "1px solid #d1d5db",
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 500,
              cursor: loading ? "default" : "pointer",
              fontFamily: "Helvetica, Arial, sans-serif",
              textAlign: "left",
            }}
          >
            {blankButtonLabel}
            <span style={{ display: "block", fontSize: 11, fontWeight: 400, color: "#9ca3af", marginTop: 2 }}>
              {blankButtonSubLabel}
            </span>
          </button>

          <button
            onClick={onCancel}
            disabled={loading}
            style={{
              padding: "6px 12px",
              background: "none",
              color: "#9ca3af",
              border: "none",
              fontSize: 12,
              cursor: "pointer",
              fontFamily: "Helvetica, Arial, sans-serif",
              alignSelf: "center",
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
