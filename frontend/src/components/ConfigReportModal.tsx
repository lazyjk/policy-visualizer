/**
 * ConfigReportModal — where-used / unused-object report for the uploaded
 * ClearPass file (POST /api/xref).
 *
 * An XML export only contains objects its services reach, so the "unused"
 * list is only complete for a DB backup (.pgdump); the modal says so.
 */
import { useEffect, useMemo, useState } from "react";
import type { XrefFinding, XrefKind, XrefObject, XrefReport } from "../api";

const KIND_LABELS: Record<XrefKind, string> = {
  role_mapping_policy: "Role mapping policies",
  enforcement_policy: "Enforcement policies",
  enforcement_profile: "Enforcement profiles",
  role: "Roles",
  auth_method: "Authentication methods",
  auth_source: "Authentication sources",
};
const KIND_ORDER = Object.keys(KIND_LABELS) as XrefKind[];

interface Props {
  report: XrefReport;
  fileName: string | null;
  onClose: () => void;
}

export default function ConfigReportModal({ report, fileName, onClose }: Props) {
  const [showBuiltin, setShowBuiltin] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const visible = useMemo(
    () => report.findings.filter((f) => showBuiltin || !f.builtin),
    [report.findings, showBuiltin],
  );
  const hiddenBuiltins = report.findings.length - report.findings.filter((f) => !f.builtin).length;

  const counts = useMemo(() => {
    const c: Record<string, { total: number; used: number }> = {};
    for (const o of report.objects) {
      const k = (c[o.kind] ??= { total: 0, used: 0 });
      k.total += 1;
      if (o.status === "used") k.used += 1;
    }
    return c;
  }, [report.objects]);

  const byObjectId = useMemo(() => new Map(report.objects.map((o) => [`${o.kind}:${o.id}`, o])), [report.objects]);

  return (
    <div style={overlayStyle} onClick={onClose} role="presentation">
      <div style={dialogStyle} onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Configuration report">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#111827" }}>Configuration report</div>
            {fileName && <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>{fileName}</div>}
          </div>
          <button onClick={onClose} style={closeStyle} aria-label="Close">✕</button>
        </div>

        {!report.complete && (
          <div style={noticeStyle}>
            An XML export only includes objects its services use, so objects that nothing uses
            can't appear here. Upload a ClearPass DB backup (.pgdump) for a complete unused-object list.
          </div>
        )}

        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, margin: "12px 0" }}>
          <tbody>
            {KIND_ORDER.filter((k) => counts[k]).map((k) => (
              <tr key={k} style={{ borderTop: "1px solid #f3f4f6" }}>
                <td style={{ padding: "4px 0", color: "#374151" }}>{KIND_LABELS[k]}</td>
                <td style={{ padding: "4px 0", textAlign: "right", color: "#6b7280", fontVariantNumeric: "tabular-nums" }}>
                  {counts[k].used} of {counts[k].total} in use
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <label style={{ fontSize: 12, color: "#374151", display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={showBuiltin} onChange={(e) => setShowBuiltin(e.target.checked)} />
          Include ClearPass built-in objects{hiddenBuiltins > 0 && !showBuiltin ? ` (${hiddenBuiltins} hidden)` : ""}
        </label>

        <FindingGroup
          title="Not used by any service"
          findings={visible.filter((f) => f.code === "unused")}
          byObjectId={byObjectId}
          empty={report.complete ? "Everything is in use." : "None in this export."}
        />
        <FindingGroup
          title="Used only by disabled services"
          findings={visible.filter((f) => f.code === "only_disabled")}
          byObjectId={byObjectId}
          empty="None."
        />
        <FindingGroup
          title="Role checks"
          findings={visible.filter((f) => f.code.startsWith("role_"))}
          byObjectId={byObjectId}
          empty="None."
          showMessage
        />
      </div>
    </div>
  );
}

function FindingGroup({
  title, findings, byObjectId, empty, showMessage = false,
}: {
  title: string;
  findings: XrefFinding[];
  byObjectId: Map<string, XrefObject>;
  empty: string;
  showMessage?: boolean;
}) {
  const grouped = KIND_ORDER
    .map((k) => [k, findings.filter((f) => f.kind === k)] as const)
    .filter(([, list]) => list.length > 0);
  return (
    <section style={{ marginTop: 16 }}>
      <div style={groupTitleStyle}>
        {title} <span style={{ color: "#9ca3af", fontWeight: 400 }}>({findings.length})</span>
      </div>
      {grouped.length === 0 ? (
        <div style={{ fontSize: 12, color: "#9ca3af" }}>{empty}</div>
      ) : (
        grouped.map(([kind, list]) => (
          <div key={kind} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 2 }}>{KIND_LABELS[kind]}</div>
            <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, lineHeight: 1.7 }}>
              {list.map((f) => {
                const users = byObjectId.get(`${f.kind}:${f.id}`)?.used_by ?? [];
                return (
                  <li key={`${f.code}:${f.kind}:${f.id}`} style={{ color: "#111827" }}>
                    {f.name}
                    {showMessage && <span style={{ color: "#6b7280" }}> — {f.message}</span>}
                    {f.code === "only_disabled" && users.length > 0 && (
                      <span style={{ color: "#6b7280" }}> — {users.map((u) => u.name).join(", ")}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}

const overlayStyle: React.CSSProperties = {
  position: "fixed", inset: 0, zIndex: 1000, background: "rgba(17, 24, 39, 0.35)",
  display: "flex", alignItems: "center", justifyContent: "center",
  fontFamily: "Helvetica, Arial, sans-serif",
};

const dialogStyle: React.CSSProperties = {
  width: "min(640px, calc(100vw - 32px))", maxHeight: "calc(100vh - 64px)", overflowY: "auto",
  background: "#fff", borderRadius: 10, padding: "18px 20px",
  boxShadow: "0 20px 40px rgba(0,0,0,0.18)",
};

const closeStyle: React.CSSProperties = {
  background: "none", border: "none", cursor: "pointer", fontSize: 16, color: "#6b7280", padding: 4,
};

const noticeStyle: React.CSSProperties = {
  marginTop: 12, padding: "8px 10px", background: "#fffbeb", border: "1px solid #fde68a",
  borderRadius: 6, fontSize: 12, color: "#92400e",
};

const groupTitleStyle: React.CSSProperties = {
  fontSize: 12, fontWeight: 700, color: "#111827", marginBottom: 6,
  textTransform: "uppercase", letterSpacing: "0.04em",
};
