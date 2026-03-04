# Policy Visualizer — Release Map to 2.0.0

## Scope Summary

This roadmap targets first public GA release `2.0.0` with:
- Export pipeline improvements (PNG/PDF/SVG)
- UI/UX enhancements (colors, snap-to-grid, annotations)
- Annotation/custom text visible in exports
- Hardening: full test sweep, determinism verification, Docker packaging validation
- Cisco ISE work limited to discovery/spec only (no ISE parser implementation in 2.0.0)

Connector routing policy baseline (implemented in interactive flow):
- Left-to-right primary progression
- Decision exits: `YES`/`PASS` on right, `NO` on bottom
- Process exits: forward/default on right, `FAIL` on bottom
- End-node entry: forward on left, `NO`/`FAIL` on top
- Chain constraints: rm/enf decisions remain fixed x-columns; actions remain to the right

## Versioning Scheme

Use strict Semantic Versioning:
- Major: breaking API/contracts or major architecture changes (`3.0.0`)
- Minor: new backward-compatible features (`2.1.0`)
- Patch: fixes only (`2.0.1`)

Pre-release ladder for 2.0:
- `2.0.0-alpha.N` → feature delivery
- `2.0.0-beta.N` → feature complete, hardening
- `2.0.0-rc.N` → release candidate freeze
- `2.0.0` → public GA

## Release Lanes

- `1.27.x`: maintenance only (bug fixes/docs/chore)
- `2.0.0-*`: active feature train → **GA released**
- `2.0.x`: maintenance patches (post-GA bug fixes, chore, docs)
- `3.0.0`: ISE integration (moved from original 2.1.0/2.2.0 plan; see release-map-3.0.md)

## Milestone Timeline

### `2.0.0-alpha.1` — Release Governance ✅ RELEASED

- Finalize SemVer and release gate policy
- Align version metadata in:
  - [api/main.py](../api/main.py)
  - [frontend/package.json](../frontend/package.json)
- Document app version vs Policy IR schema version distinction in:
  - [src/policy_ir.py](../src/policy_ir.py)
  - [claude.md](../claude.md)

Exit criteria:
- Version policy documented and agreed
- Backend/frontend version touchpoints identified and consistent

### `2.0.0-alpha.2` — Export Foundation ✅ RELEASED

- Client-side PNG/PDF export of the React Flow canvas (no backend route):
  - Add `html-to-image` and `jspdf` npm dependencies
  - [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx):
    `ExportPanel` component with "Export PNG" / "Export PDF" buttons; captures
    the full diagram via `fitView` before capture, excludes UI chrome, restores
    viewport after

Exit criteria:
- Current diagram can be exported as PNG/PDF (captures exactly what is on screen)
- Full diagram is always captured regardless of current zoom/pan state

### `2.0.0-alpha.2.5` — Export Refinements ✅ RELEASED _(interim drop)_

Interim drop on top of alpha.2 (no separate ticket):
- SVG export added alongside PNG/PDF
- White background default for all export formats
- Transparency toggle (checkbox) controls white vs. transparent background

### `2.0.0-alpha.3` — Annotation and Custom Text ✅ RELEASED

- Add annotation/custom text UI:
  - [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)
  - [frontend/src/components/nodes/nodeTypes.tsx](../frontend/src/components/nodes/nodeTypes.tsx)
- Annotation nodes: sticky notes with inline editing, connectable with dashed arrows
- Ensure annotation/custom text appears in exported PNG/PDF/SVG

Exit criteria:
- User-authored text is visible in both UI and exports
- Deterministic behavior validated for repeated export of same payload

### `2.0.0-alpha.4` — UX Interaction Pack ✅ RELEASED _(partial — see deferred below)_

Shipped:
- Per-shape node color picker (6 node types): [frontend/src/components/nodes/nodeTypes.tsx](../frontend/src/components/nodes/nodeTypes.tsx)
- Snap-to-grid toggle: [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)

Not shipped (moved to post-GA deferred — see below):
- UX-230: Session drag persistence
- UX-231: Auto-align action
- UX-233: Multi-service tabbed viewing

Exit criteria met:
- Color selections reflected consistently and export-visible
- Snap-to-grid functional and stable

### `2.0.0-beta.1` — Vertical Collapse v1 ❌ PERMANENTLY ABANDONED

> **Status**: Implementation attempted and permanently abandoned. The chain
> compression post-process in `applyDagreLayout` conflicts with collapsed summary
> nodes (wrong x-positions). The `buildVisibleGraph` absorption also needs to be
> iterative (decision → action → end), not one-shot. See Epic COL below.
> Root-cause analysis preserved at `~/.claude/plans/cozy-enchanting-cocoa.md`.

- Implement vertical chain collapse/expand for:
  - role-mapping decision chain
  - enforcement decision chain
- Use existing `rank_group` hooks from:
  - [src/flow_ir.py](../src/flow_ir.py)
- Frontend behavior in:
  - [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)

Exit criteria (when scheduled):
- Collapse/expand preserves semantic flow
- Edge rewiring remains correct and reversible

### `2.0.0-beta.2` — Hardening & Stabilization ✅ RELEASED

Pure hardening milestone — no new features. Scope:
- Full 71-test pass sweep (confirm no regressions from alpha.3/alpha.4 features)
- API boundary and error-response validation:
  - [tests/test_api_routes.py](../tests/test_api_routes.py)
  - [tests/test_flow_ir.py](../tests/test_flow_ir.py)
- Determinism verification: same XML → same graph across repeated calls
- Docker packaging validation: `docker compose up --build` clean cold-start
- Release notes for beta.2

Exit criteria:
- All 71 tests pass with no failures
- Docker compose cold-start produces a working app
- No regressions from alpha.3/alpha.4 (annotations, color picker, snap-to-grid)
- Determinism confirmed for all existing test fixtures
- Release notes drafted

### `2.0.0-rc.1` — Release Candidate ✅ RELEASED

- Feature freeze
- Docs and packaging verification:
  - [docker-compose.yml](../docker-compose.yml)
  - [claude.md](../claude.md)

Exit criteria:
- Release notes drafted
- Packaging and runbook validated

### `2.0.0` — Public GA ✅ RELEASED

- Tag and publish with final changelog
- Maintain patch cadence via `2.0.x`

---

## Ticketized Backlog

## Epic REL — Release Governance & Versioning

- ✅ REL-201: Define SemVer rules and release gates in [claude.md](../claude.md)
  Acceptance: major/minor/patch + alpha/beta/rc criteria documented.

- ✅ REL-202: Align backend app version metadata in [api/main.py](../api/main.py)
  Acceptance: API metadata reflects release tag.

- ✅ REL-203: Align frontend package version in [frontend/package.json](../frontend/package.json)
  Acceptance: package version follows release tag policy.

- ✅ REL-204: Document app version vs Policy IR schema version in [src/policy_ir.py](../src/policy_ir.py) and [claude.md](../claude.md)
  Acceptance: clear distinction and version bump rules are explicit.

## Epic EXP — Export Pipeline

- ✅ EXP-210: Add `html-to-image` + `jspdf` npm deps; implement client-side capture
  in [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)
  Acceptance: PNG/PDF export captures the React Flow canvas (not the Graphviz renderer);
  full diagram captured regardless of zoom/pan; UI chrome excluded from output.
  _(No backend route — export is entirely client-side.)_
  _Note: SVG export + transparency toggle shipped in alpha.2.5 (interim drop, no separate ticket)._

- ✅ EXP-211: ~~Add frontend export controls~~ — merged into EXP-210.

- ✅ EXP-212: ~~Add API export test coverage~~ — removed (no new API route).

## Epic ANN — Annotations & Custom Text

- ✅ ANN-220: Define annotation data model and behavior in [claude.md](../claude.md)
  Acceptance: supports customer-facing export use.

- ✅ ANN-221: Implement annotation and box-text customization UI in [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx) and [frontend/src/components/nodes/nodeTypes.tsx](../frontend/src/components/nodes/nodeTypes.tsx)
  Acceptance: users can add/edit text attached to diagram context.

- ✅ ANN-222: Ensure annotations are rendered in export output via API/renderer path
  Acceptance: exported artifact matches on-screen content.

## Epic UX — Interaction and Multi-Service UX

- ✅ UX-232: Add customizable node colors in [frontend/src/components/nodes/nodeTypes.tsx](../frontend/src/components/nodes/nodeTypes.tsx)
  Acceptance: color selections are reflected consistently and export-visible.
  _Shipped: alpha.4._

- ❌ UX-230: Session drag persistence — **won't fix** (low user demand vs. complexity; not worth the state-management overhead post-GA).
- ❌ UX-231: Auto-align action — **won't fix** (edge-case utility; conflicts with user manual layout intent).
- ❌ UX-233: Multi-service tabbed flow viewing — **won't fix** (deferred to 3.0 track if ISE multi-service model needs it).

- ⏸ UX-234: Expose `HORIZ_GAP` constant as a user-adjustable toolbar input
  (slider or number input) in [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)
  Hook: `// TODO(interactive)` comment at ~line 159.
  Acceptance: user can adjust horizontal column spacing; change reflected live without reloading the diagram.
  Target: 2.1.0.

## Epic COL — Vertical Collapse v1 ❌ WON'T FIX

> **Status**: Permanently abandoned. Implementation was attempted and reverted.
> Root cause: the chain compression post-process in `applyDagreLayout` conflicts
> with collapsed summary nodes (wrong x-positions); `buildVisibleGraph` absorption
> would also need to be iterative rather than one-shot.
> Root-cause analysis preserved at `~/.claude/plans/cozy-enchanting-cocoa.md`.
> Infrastructure hook (`rank_group` on FlowNode) remains in place but is unused.

- ❌ COL-240: Implement vertical chain collapse/expand — **won't fix** (see epic note above).

- ❌ COL-241: Add collapse behavior tests — **won't fix** (no implementation to test).

## Epic ISE — ➡ Moved to 3.0 Track

> **Note:** ISE integration has been moved from the originally planned `2.1.0` to the
> `3.0.0` major release track. ISE's policy model (Policy Sets, AuthN/AuthZ policies,
> SGTs) is expected to require breaking changes to the `PolicyIR` schema, warranting a
> major version bump. See `docs/release-map-3.0.md` for the 3.0 roadmap.

- ➡ ISE-250: ISE-to-IR mapping matrix → moved to 3.0-alpha.1
- ➡ ISE-251: Fixture strategy → moved to 3.0-alpha.1
- ➡ ISE-252: Architecture decision record → moved to 3.0-alpha.1

---

## Open — Post-2.0.0 GA

Items with infrastructure hooks in place, explicitly scheduled or open for 2.1.0+.
**Do not implement until explicitly scheduled.**

- **[NEXT] ANN-223**: Replace plain-textarea annotation editing with a mini WYSIWYG editor
  (bold, italic, bullet lists) in [frontend/src/components/nodes/nodeTypes.tsx](../frontend/src/components/nodes/nodeTypes.tsx)
  Acceptance: formatted text renders correctly in both the diagram UI and all export formats.
  Hook: `// TODO(wysiwyg)` comment on `AnnotationNode` in nodeTypes.tsx.
  Target: `2.1.0`.

- UX-234: Expose `HORIZ_GAP` as a user-adjustable toolbar input in [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)
  Hook: `// TODO(interactive)` at ~line 159.
  Target: `2.1.0`.

**ISE integration** → moved to 3.0 track (see Epic ISE above).

**Closed items** (UX-230, UX-231, UX-233, COL-240, COL-241) — marked won't-fix in their respective epics above.

---

## Release Gates

- Alpha gate: export + annotation baseline complete ✅
- Beta gate: no critical defects; all 71 tests pass; Docker packaging validated
- RC gate: full test pass + packaging validation + docs complete
- GA gate: tagged release + final release notes + patch support plan
