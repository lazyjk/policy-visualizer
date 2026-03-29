import { useState } from "react";
import type { BuilderPlatform, ClearPassElements, ISEElements, BuilderElements } from "../../api/builderApi";

interface Props {
  elements: BuilderElements;
  platform: BuilderPlatform;
}

interface Section {
  key: string;
  label: string;
  items: Record<string, unknown>[];
  badgeColor?: string;
}

function buildSections(elements: BuilderElements, platform: BuilderPlatform): Section[] {
  if (platform === "clearpass") {
    const e = elements as ClearPassElements;
    return [
      { key: "services", label: "Services", items: e.services, badgeColor: "#dbeafe" },
      { key: "roles", label: "Roles", items: e.roles, badgeColor: "#fce7f3" },
      { key: "enforcement_profiles", label: "Enforcement Profiles", items: e.enforcement_profiles, badgeColor: "#ede9fe" },
      { key: "enforcement_policies", label: "Enforcement Policies", items: e.enforcement_policies, badgeColor: "#fef3c7" },
      { key: "role_mapping_policies", label: "Role Mapping Policies", items: e.role_mapping_policies, badgeColor: "#d1fae5" },
      { key: "auth_methods", label: "Authentication Methods", items: e.auth_methods, badgeColor: "#fee2e2" },
      { key: "auth_sources", label: "Authentication Sources", items: e.auth_sources, badgeColor: "#ffedd5" },
    ];
  }
  const e = elements as ISEElements;
  return [
    { key: "radius_policy_sets", label: "RADIUS Policy Sets", items: e.radius_policy_sets, badgeColor: "#dbeafe" },
    { key: "tacacs_policy_sets", label: "TACACS Policy Sets", items: e.tacacs_policy_sets, badgeColor: "#ede9fe" },
    { key: "profiles", label: "Authorization Profiles", items: e.profiles, badgeColor: "#fef3c7" },
    { key: "identity_stores", label: "Identity Stores", items: e.identity_stores, badgeColor: "#d1fae5" },
  ];
}

function getItemName(item: Record<string, unknown>): string {
  return (
    (item.name as string | undefined) ??
    (item.id as string | undefined) ??
    "(unnamed)"
  );
}

function getItemType(item: Record<string, unknown>): string | null {
  return (
    (item.service_type as string | undefined) ??
    (item.profile_type as string | undefined) ??
    (item.set_type as string | undefined) ??
    (item.access_type as string | undefined) ??
    null
  );
}

type CanDragProp = boolean | ((sectionKey: string) => boolean);

export default function ElementsLibrary({ elements, platform, canDrag = false }: Props & { canDrag?: CanDragProp }) {
  const sections = buildSections(elements, platform);
  const totalItems = sections.reduce((n, s) => n + s.items.length, 0);

  const [filterText, setFilterText] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(sections.slice(0, 2).map((s) => s.key))
  );

  const warnings = (elements as ClearPassElements).warnings ??
    (elements as ISEElements).warnings ?? [];

  function toggleSection(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function filterItems(items: Record<string, unknown>[]) {
    if (!filterText) return items;
    const lower = filterText.toLowerCase();
    return items.filter((item) =>
      getItemName(item).toLowerCase().includes(lower)
    );
  }

  return (
    <div style={{ fontFamily: "Helvetica, Arial, sans-serif", fontSize: 13 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 14 }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: "#111827" }}>
          Policy Elements
        </span>
        <span style={{ color: "#9ca3af", fontSize: 12 }}>
          {totalItems.toLocaleString()} items across {sections.length} types
        </span>
      </div>

      {/* Warnings */}
      {warnings.length > 0 && (
        <div style={{
          background: "#fef3c7",
          border: "1px solid #f59e0b",
          borderRadius: 5,
          padding: "8px 12px",
          marginBottom: 14,
          fontSize: 12,
          color: "#92400e",
        }}>
          <strong>Partial result</strong> — some element types could not be fetched:
          <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
            {warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

      {/* Filter */}
      <input
        type="search"
        placeholder="Filter elements…"
        value={filterText}
        onChange={(e) => setFilterText(e.target.value)}
        style={{
          width: "100%",
          boxSizing: "border-box",
          padding: "7px 10px",
          border: "1px solid #d1d5db",
          borderRadius: 5,
          fontSize: 13,
          fontFamily: "inherit",
          marginBottom: 12,
          background: "#f9fafb",
        }}
      />

      {/* Accordion sections */}
      {sections.map((section) => {
        const filtered = filterItems(section.items);
        const isOpen = expanded.has(section.key) || filterText.length > 0;

        const isDraggable = typeof canDrag === "function" ? canDrag(section.key) : (canDrag ?? false);

        return (
          <div key={section.key} style={{ marginBottom: 4 }}>
            {/* Section header */}
            <button
              onClick={() => toggleSection(section.key)}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 10px",
                background: isOpen ? "#f3f4f6" : "#fff",
                border: "1px solid #e5e7eb",
                borderRadius: isOpen ? "5px 5px 0 0" : 5,
                fontFamily: "inherit",
                fontSize: 13,
                fontWeight: 600,
                color: "#374151",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 10, color: "#9ca3af" }}>
                  {isOpen ? "▼" : "▶"}
                </span>
                {section.label}
              </span>
              <span style={{
                background: section.badgeColor ?? "#e5e7eb",
                borderRadius: 10,
                padding: "1px 8px",
                fontSize: 11,
                fontWeight: 700,
                color: "#374151",
              }}>
                {section.items.length}
              </span>
            </button>

            {/* Items */}
            {isOpen && (
              <div style={{
                border: "1px solid #e5e7eb",
                borderTop: "none",
                borderRadius: "0 0 5px 5px",
                maxHeight: 280,
                overflowY: "auto",
              }}>
                {filtered.length === 0 ? (
                  <div style={{ padding: "10px 14px", color: "#9ca3af", fontStyle: "italic" }}>
                    {filterText ? "No matches" : "No items"}
                  </div>
                ) : (
                  filtered.map((item, i) => {
                    const name = getItemName(item);
                    const type = getItemType(item);
                    return (
                      <div
                        key={i}
                        draggable={isDraggable}
                        onDragStart={isDraggable ? (e) => {
                          e.dataTransfer.effectAllowed = "copy";
                          e.dataTransfer.setData(
                            "application/builder-item",
                            JSON.stringify({ sectionKey: section.key, item })
                          );
                        } : undefined}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "6px 14px",
                          borderBottom: i < filtered.length - 1 ? "1px solid #f3f4f6" : "none",
                          background: "#fff",
                          cursor: isDraggable ? "grab" : "default",
                        }}
                      >
                        {isDraggable && (
                          <span style={{ color: "#d1d5db", fontSize: 10, marginRight: 6, userSelect: "none" }}>⠿</span>
                        )}
                        <span style={{ color: "#111827", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                          {name}
                        </span>
                        {type && (
                          <span style={{
                            marginLeft: 8,
                            fontSize: 10,
                            fontWeight: 600,
                            color: "#6b7280",
                            background: "#f3f4f6",
                            borderRadius: 3,
                            padding: "1px 5px",
                            whiteSpace: "nowrap",
                          }}>
                            {type}
                          </span>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
