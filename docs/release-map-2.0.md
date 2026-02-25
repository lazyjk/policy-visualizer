# Policy Visualizer — Release Map to 2.0.0

## Scope Summary

This roadmap targets first public GA release `2.0.0` with:
- Export pipeline improvements (PNG/PDF)
- UI/UX enhancements (colors, drag persistence, alignment, multi-service tabs)
- Annotation/custom text visible in exports
- Vertical chain collapse/expand (role/enforcement chains only)
- Cisco ISE work limited to discovery/spec only (no ISE parser implementation in 2.0.0)

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
- `2.0.0-*`: active feature train
- `2.1.0`: reserved for ISE import implementation
- `2.2.0+`: reserved for ISE export (if feasible after import parity)

## Milestone Timeline

### `2.0.0-alpha.1` — Release Governance
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

### `2.0.0-alpha.2` — Export Foundation
- Client-side PNG/PDF export of the React Flow canvas (no backend route):
  - Add `html-to-image` and `jspdf` npm dependencies
  - [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx):
    `ExportPanel` component with "Export PNG" / "Export PDF" buttons; captures
    the full diagram via `fitView` before capture, excludes UI chrome, restores
    viewport after

Exit criteria:
- Current diagram can be exported as PNG/PDF (captures exactly what is on screen)
- Full diagram is always captured regardless of current zoom/pan state

### `2.0.0-alpha.3` — Annotation and Custom Text
- Add annotation/custom text UI:
  - [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)
  - [frontend/src/components/nodes/nodeTypes.tsx](../frontend/src/components/nodes/nodeTypes.tsx)
- Ensure annotation/custom text appears in exported PNG/PDF

Exit criteria:
- User-authored text is visible in both UI and exports
- Deterministic behavior validated for repeated export of same payload

### `2.0.0-alpha.4` — UX Interaction Pack
- Persist drag positions for current working session
- Add explicit auto-align action
- Add customizable node color support
- Add multi-service tabbed viewing (no graph merging):
  - [frontend/src/App.tsx](../frontend/src/App.tsx)
  - [frontend/src/components/UploadPanel.tsx](../frontend/src/components/UploadPanel.tsx)
  - [frontend/src/api.ts](../frontend/src/api.ts)

Exit criteria:
- Node drag remains stable with intact edges
- Multi-service flows are switchable via tabs
- Alignment action produces a clean deterministic layout

### `2.0.0-beta.1` — Vertical Collapse v1
- Implement vertical chain collapse/expand for:
  - role-mapping decision chain
  - enforcement decision chain
- Use existing `rank_group` hooks from:
  - [src/flow_ir.py](../src/flow_ir.py)
- Frontend behavior in:
  - [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)

Exit criteria:
- Collapse/expand preserves semantic flow
- Edge rewiring remains correct and reversible

### `2.0.0-beta.2` — Hardening
- Regression and edge-case fixes
- Determinism and API test pass sweep:
  - [tests/test_api_routes.py](../tests/test_api_routes.py)
  - [tests/test_flow_ir.py](../tests/test_flow_ir.py)
  - [tests](../tests)

Exit criteria:
- No critical defects
- Stable outputs for repeated identical inputs

### `2.0.0-rc.1` — Release Candidate
- Feature freeze
- Docs and packaging verification:
  - [docker-compose.yml](../docker-compose.yml)
  - [claude.md](../claude.md)

Exit criteria:
- Release notes drafted
- Packaging and runbook validated

### `2.0.0` — Public GA
- Tag and publish with final changelog
- Maintain patch cadence via `2.0.x`

## Ticketized Backlog

## Epic REL — Release Governance & Versioning

- REL-201: Define SemVer rules and release gates in [claude.md](../claude.md)  
  Acceptance: major/minor/patch + alpha/beta/rc criteria documented.

- REL-202: Align backend app version metadata in [api/main.py](../api/main.py)  
  Acceptance: API metadata reflects release tag.

- REL-203: Align frontend package version in [frontend/package.json](../frontend/package.json)  
  Acceptance: package version follows release tag policy.

- REL-204: Document app version vs Policy IR schema version in [src/policy_ir.py](../src/policy_ir.py) and [claude.md](../claude.md)  
  Acceptance: clear distinction and version bump rules are explicit.

## Epic EXP — Export Pipeline

- EXP-210: Add `html-to-image` + `jspdf` npm deps; implement client-side capture
  in [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)
  Acceptance: PNG/PDF export captures the React Flow canvas (not the Graphviz renderer);
  full diagram captured regardless of zoom/pan; UI chrome excluded from output.
  _(No backend route — export is entirely client-side.)_

- EXP-211: ~~Add frontend export controls~~ — merged into EXP-210.

- EXP-212: ~~Add API export test coverage~~ — removed (no new API route).

## Epic ANN — Annotations & Custom Text

- ANN-220: Define annotation data model and behavior in [claude.md](../claude.md)  
  Acceptance: supports customer-facing export use.

- ANN-221: Implement annotation and box-text customization UI in [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx) and [frontend/src/components/nodes/nodeTypes.tsx](../frontend/src/components/nodes/nodeTypes.tsx)  
  Acceptance: users can add/edit text attached to diagram context.

- ANN-222: Ensure annotations are rendered in export output via API/renderer path  
  Acceptance: exported artifact matches on-screen content.

## Epic UX — Interaction and Multi-Service UX

- UX-230: Session drag persistence in [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)  
  Acceptance: nodes remain where placed during workflow.

- UX-231: Add auto-align action in [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx)  
  Acceptance: diagram can be normalized to clean vertical/horizontal alignment.

- UX-232: Add customizable node colors in [frontend/src/components/nodes/nodeTypes.tsx](../frontend/src/components/nodes/nodeTypes.tsx)  
  Acceptance: color selections are reflected consistently and export-visible.

- UX-233: Add multi-service tabbed flow viewing in [frontend/src/App.tsx](../frontend/src/App.tsx), [frontend/src/components/UploadPanel.tsx](../frontend/src/components/UploadPanel.tsx), and [frontend/src/api.ts](../frontend/src/api.ts)  
  Acceptance: multiple services viewable in tabs; no merged graph.

## Epic COL — Vertical Collapse v1

- COL-240: Implement vertical chain collapse/expand in [frontend/src/components/FlowDiagram.tsx](../frontend/src/components/FlowDiagram.tsx) using `rank_group` from [src/flow_ir.py](../src/flow_ir.py)  
  Acceptance: rm/enf chains collapse and expand without semantic breakage.

- COL-241: Add collapse behavior tests in [tests/test_flow_ir.py](../tests/test_flow_ir.py) and frontend test harness (if present)  
  Acceptance: edge correctness and restore behavior verified.

## Epic ISE — Discovery/Spec Only (2.0 Scope)

- ISE-250: Create ISE-to-IR mapping matrix using [src/parser.py](../src/parser.py), [src/policy_ir.py](../src/policy_ir.py), [src/flow_ir.py](../src/flow_ir.py)  
  Acceptance: mapping coverage, assumptions, and gaps documented.

- ISE-251: Define fixtures and determinism test strategy in [tests](../tests)  
  Acceptance: proposed fixture set and validation approach approved.

- ISE-252: Publish implementation recommendation for `2.1.0` ISE import  
  Acceptance: scope, risks, and phased estimate approved; no production ISE parser code in `2.0.0`.

## Deferred — Post-2.0.0 GA

Items with infrastructure hooks in place but intentionally out of 2.0.0 scope.
**Do not implement until explicitly scheduled.**

- ANN-223: Replace plain-textarea annotation editing with a mini WYSIWYG editor
  (bold, italic, bullet lists) in [frontend/src/components/nodes/nodeTypes.tsx](../frontend/src/components/nodes/nodeTypes.tsx)
  Acceptance: formatted text renders correctly in both the diagram UI and all export formats.
  Hook: `// TODO(wysiwyg)` comment on `AnnotationNode` in nodeTypes.tsx.
  Target: `2.1.0` or later.

## Release Gates

- Alpha gate: export + base UX + annotation baseline complete
- Beta gate: vertical collapse complete; no critical defects
- RC gate: full test pass + packaging validation + docs complete
- GA gate: tagged release + final release notes + patch support plan
