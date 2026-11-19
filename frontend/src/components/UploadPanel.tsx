/**
 * UploadPanel — file upload (XML export or ClearPass DB backup) and service picker.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { ServiceSummary } from "../api";
import { templateLabel } from "../serviceLabels";

interface Props {
  services: ServiceSummary[];
  selectedService: string | null;
  fileName: string | null;
  loading: boolean;
  error: string | null;
  onFileSelect: (file: File) => void;
  onServiceSelect: (id: string) => void;
  /** Opens the where-used / unused-object report; undefined while unavailable. */
  onOpenReport?: () => void;
}

export default function UploadPanel({
  services,
  selectedService,
  fileName,
  loading,
  error,
  onFileSelect,
  onServiceSelect,
  onOpenReport,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [filterType, setFilterType] = useState<string>("");
  const [nameFilter, setNameFilter] = useState<string>("");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc" | "none">("none");

  // Reset controls when a new file is loaded
  useEffect(() => {
    setFilterType("");
    setNameFilter("");
    setSortOrder("none");
  }, [services]);

  // Real services exclude ClearPass "------Name------" divider entries.
  const realServiceCount = useMemo(() => services.filter((s) => !s.is_category).length, [services]);
  // Only a DB backup carries ClearPass evaluation order; an XML export is
  // grouped by service type instead.
  const hasPrecedence = useMemo(() => services.some((s) => s.precedence != null), [services]);
  const plainView = !filterType && !nameFilter.trim() && sortOrder === "none";

  const displayedServices = useMemo(() => {
    const position = (s: ServiceSummary, i: number) =>
      hasPrecedence ? (s.precedence ?? Number.MAX_SAFE_INTEGER) : (s.export_order ?? i);
    let list = services
      .map((s, i) => ({ s, i }))
      .sort((a, b) => position(a.s, a.i) - position(b.s, b.i) || a.i - b.i)
      .map(({ s }) => s);
    // ClearPass "------Name------" divider services carry no policy. In true
    // evaluation order (DB backup, unsorted, unfiltered) they become section
    // headers; anywhere else their position means nothing, so they're hidden.
    if (!(hasPrecedence && plainView)) list = list.filter((s) => !s.is_category);
    if (filterType) list = list.filter((s) => s.service_type === filterType);
    if (nameFilter.trim()) {
      const raw = nameFilter.trim();
      const negate = raw.startsWith("!");
      const q = (negate ? raw.slice(1) : raw).toLowerCase();
      if (q) list = list.filter((s) =>
        negate ? !s.name.toLowerCase().includes(q) : s.name.toLowerCase().includes(q)
      );
    }
    if (sortOrder === "asc") list.sort((a, b) => a.name.localeCompare(b.name));
    else if (sortOrder === "desc") list.sort((a, b) => b.name.localeCompare(a.name));
    return list;
  }, [services, filterType, nameFilter, sortOrder, hasPrecedence, plainView]);

  function cycleSortOrder() {
    setSortOrder((prev) => (prev === "none" ? "asc" : prev === "asc" ? "desc" : "none"));
  }

  function handleFile(file: File) {
    if (!/\.(xml|pgdump|dump)$/i.test(file.name)) {
      alert("Please upload an XML export (.xml) or a ClearPass DB backup (.pgdump).");
      return;
    }
    onFileSelect(file);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  return (
    <div style={panelStyle}>
      <img
        src="/policy_visualizer_logo.svg"
        alt="Policy Visualizer"
        style={{ display: "block", width: "100%", marginBottom: 16 }}
      />

      {/* Drop zone */}
      <div
        style={{
          ...dropZoneStyle,
          borderColor: dragging ? "#6366f1" : "#d1d5db",
          background: dragging ? "#eef2ff" : "#f9fafb",
        }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".xml,.pgdump,.dump"
          style={{ display: "none" }}
          onChange={handleChange}
        />
        <span style={{ fontSize: 28 }}>📁</span>
        <p style={{ margin: "8px 0 0", fontSize: 13, color: "#6b7280" }}>
          {loading
            ? "Processing…"
            : "Drop a service/policy XML export or a ClearPass DB backup (.pgdump) here, or click to browse"}
        </p>
      </div>

      {/* Current file */}
      {fileName && (
        <div style={fileNameStyle}>
          <span style={{ marginRight: 6 }}>📄</span>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {fileName}
          </span>
        </div>
      )}

      {onOpenReport && (
        <button onClick={onOpenReport} style={reportButtonStyle} title="Where objects are used, and what nothing uses">
          Configuration report
        </button>
      )}

      {/* Error */}
      {error && (
        <div style={errorStyle}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Service picker */}
      {services.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <p style={{ margin: "0 0 2px", fontSize: 13, fontWeight: 500 }}>
            Select a service to visualize:
          </p>
          <p style={{ margin: "0 0 8px", fontSize: 10, color: "#9ca3af" }}>
            {hasPrecedence
              ? "Listed in ClearPass evaluation order"
              : "Listed in export file order — upload a DB backup for evaluation order"}
          </p>

          {/* Filter + sort controls — only shown when there are multiple services */}
          {realServiceCount > 1 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 8 }}>
              {/* Name filter + sort icon */}
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  type="text"
                  value={nameFilter}
                  onChange={(e) => setNameFilter(e.target.value)}
                  placeholder="Filter by name…"
                  style={nameFilterStyle}
                  aria-label="Filter services by name"
                />
                <button
                  onClick={cycleSortOrder}
                  style={{
                    ...sortIconButtonStyle,
                    ...(sortOrder !== "none" ? sortIconButtonActiveStyle : {}),
                  }}
                  title={sortOrder === "none" ? "Sort A → Z" : sortOrder === "asc" ? "Sort Z → A" : "Clear sort"}
                  aria-label="Toggle sort order"
                >
                  <SortAZIcon order={sortOrder} />
                </button>
              </div>
              {/* Negation hint */}
              {nameFilter.startsWith("!") && nameFilter.length > 1 && (
                <p style={{ margin: 0, fontSize: 11, color: "#6366f1" }}>
                  Excluding "<strong>{nameFilter.slice(1)}</strong>"
                </p>
              )}
              {nameFilter === "!" && (
                <p style={{ margin: 0, fontSize: 11, color: "#9ca3af" }}>
                  Type a term after ! to exclude it
                </p>
              )}
              {!nameFilter && (
                <p style={{ margin: 0, fontSize: 10, color: "#9ca3af" }}>
                  Tip: prefix with <code style={{ fontFamily: "monospace" }}>!</code> to exclude, e.g. <code style={{ fontFamily: "monospace" }}>!test</code>
                </p>
              )}
              {/* Type filter */}
              <select
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                style={controlSelectStyle}
                aria-label="Filter by service type"
              >
                <option value="">All types</option>
                <option value="RADIUS">RADIUS</option>
                <option value="TACACS">TACACS</option>
                <option value="RADIUS_PROXY">RADIUS PROXY</option>
                <option value="WEBAUTH">WEBAUTH</option>
                <option value="APPLICATION">APPLICATION</option>
              </select>
            </div>
          )}

          {displayedServices.length === 0 ? (
            <p style={{ margin: 0, fontSize: 12, color: "#9ca3af" }}>No services match.</p>
          ) : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {displayedServices.map((svc) => {
                if (svc.is_category) {
                  return (
                    <li key={svc.id} style={sectionHeaderStyle}>
                      {svc.name.replace(/^-+|-+$/g, "").trim() || svc.name}
                    </li>
                  );
                }
                const isActive = svc.id === selectedService;
                const enabled = svc.enabled !== false;
                const tmpl = templateLabel(svc.template ?? "");
                return (
                  <li key={svc.id} style={{ marginBottom: 6 }}>
                    <button
                      style={{
                        ...(isActive ? activeServiceButtonStyle : serviceButtonStyle),
                        ...(enabled ? {} : { opacity: isActive ? 0.8 : 0.55 }),
                      }}
                      onClick={() => onServiceSelect(svc.id)}
                      title={[svc.description, enabled ? "" : "Disabled in ClearPass"].filter(Boolean).join("\n") || undefined}
                    >
                      {hasPrecedence && svc.precedence != null && (
                        <span style={precedenceStyle}>{svc.precedence}</span>
                      )}
                      <span>{svc.name}</span>
                      <span style={serviceTypeBadgeStyle}>{svc.service_type}</span>
                      {tmpl && tmpl !== svc.service_type && (
                        <span style={serviceTypeBadgeStyle}>{tmpl}</span>
                      )}
                      {!enabled && <span style={disabledBadgeStyle}>Disabled</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

const panelStyle: React.CSSProperties = {
  width: 280,
  minWidth: 280,
  background: "#fff",
  borderRight: "1px solid #e5e7eb",
  padding: "20px 16px",
  overflowY: "auto",
  fontFamily: "Helvetica, Arial, sans-serif",
};

const dropZoneStyle: React.CSSProperties = {
  border: "2px dashed",
  borderRadius: 8,
  padding: "24px 16px",
  textAlign: "center",
  cursor: "pointer",
  transition: "border-color 0.15s, background 0.15s",
};

const fileNameStyle: React.CSSProperties = {
  marginTop: 12,
  padding: "8px 10px",
  background: "#f0fdf4",
  border: "1px solid #bbf7d0",
  borderRadius: 6,
  fontSize: 12,
  color: "#15803d",
  display: "flex",
  alignItems: "center",
};

const reportButtonStyle: React.CSSProperties = {
  marginTop: 8,
  width: "100%",
  padding: "6px 10px",
  fontSize: 12,
  fontFamily: "inherit",
  color: "#4338ca",
  background: "#eef2ff",
  border: "1px solid #c7d2fe",
  borderRadius: 6,
  cursor: "pointer",
};

const errorStyle: React.CSSProperties = {
  marginTop: 12,
  padding: "10px 12px",
  background: "#fef2f2",
  border: "1px solid #fca5a5",
  borderRadius: 6,
  fontSize: 12,
  color: "#dc2626",
};

const serviceButtonStyle: React.CSSProperties = {
  width: "100%",
  textAlign: "left",
  padding: "8px 10px",
  background: "#f3f4f6",
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 12,
  fontFamily: "inherit",
  color: "#111827",
};

const activeServiceButtonStyle: React.CSSProperties = {
  ...serviceButtonStyle,
  background: "#eef2ff",
  border: "1px solid #6366f1",
  color: "#4338ca",
  fontWeight: 600,
};

const controlSelectStyle: React.CSSProperties = {
  flex: 1,
  fontSize: 11,
  padding: "4px 6px",
  border: "1px solid #e5e7eb",
  borderRadius: 5,
  background: "#f9fafb",
  color: "#374151",
  fontFamily: "inherit",
  cursor: "pointer",
};

const serviceTypeBadgeStyle: React.CSSProperties = {
  marginLeft: 6,
  fontSize: 10,
  fontWeight: 600,
  color: "#6b7280",
  background: "#e5e7eb",
  borderRadius: 4,
  padding: "1px 5px",
  verticalAlign: "middle",
};

const sectionHeaderStyle: React.CSSProperties = {
  margin: "10px 0 6px",
  padding: "0 2px 2px",
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "#6b7280",
  borderBottom: "1px solid #e5e7eb",
};

const precedenceStyle: React.CSSProperties = {
  display: "inline-block",
  minWidth: 18,
  marginRight: 6,
  fontSize: 10,
  color: "#9ca3af",
  fontVariantNumeric: "tabular-nums",
};

const disabledBadgeStyle: React.CSSProperties = {
  ...serviceTypeBadgeStyle,
  color: "#991b1b",
  background: "#fee2e2",
};

const nameFilterStyle: React.CSSProperties = {
  flex: 1,
  fontSize: 11,
  padding: "4px 8px",
  border: "1px solid #e5e7eb",
  borderRadius: 5,
  background: "#f9fafb",
  color: "#374151",
  fontFamily: "inherit",
  outline: "none",
};

const sortIconButtonStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: 30,
  minWidth: 30,
  height: 28,
  border: "1px solid #e5e7eb",
  borderRadius: 5,
  background: "#f9fafb",
  cursor: "pointer",
  padding: 0,
};

const sortIconButtonActiveStyle: React.CSSProperties = {
  border: "1px solid #6366f1",
  background: "#eef2ff",
};

function SortAZIcon({ order }: { order: "asc" | "desc" | "none" }) {
  const arrow = order === "asc" ? "↑" : order === "desc" ? "↓" : "↕";
  return (
    <svg width="22" height="20" viewBox="0 0 22 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <text x="1" y="9" fontSize="8" fontWeight="700" fontFamily="Helvetica, Arial, sans-serif"
        fill={order !== "none" ? "#4338ca" : "#6b7280"}>A</text>
      <text x="1" y="18" fontSize="8" fontWeight="700" fontFamily="Helvetica, Arial, sans-serif"
        fill={order !== "none" ? "#4338ca" : "#6b7280"}>Z</text>
      <text x="13" y="14" fontSize="11" fontFamily="Helvetica, Arial, sans-serif"
        fill={order !== "none" ? "#4338ca" : "#6b7280"}>{arrow}</text>
    </svg>
  );
}
