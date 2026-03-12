# Feature Spec: Policy Details Inspector + Documentation Appendix

- Owner: Policy Visualizer team
- Status: Draft
- Target release: TBD
- Last updated: 2026-03-10

## 1. Problem Statement

Policy flow diagrams are intentionally concise and structurally focused. Today, users can inspect topology and sequence, but they cannot easily read full policy element details (for example role mapping rule logic, authentication behavior, or enforcement rule actions) in a single reader-friendly view.

This creates friction for:
- Deep troubleshooting and policy validation workflows.
- Audit and documentation workflows that require policy detail context alongside visual flow.

The feature must improve policy detail readability without interfering with diagram layout, interaction model, or determinism.

## 2. Goals

1. Provide a non-intrusive, reader-friendly way to view detailed policy elements from the flow diagram.
2. Preserve existing flow diagram behavior and visual integrity (no layout disruption).
3. Support both ClearPass and Cisco ISE pipelines with parity at the UX and data-contract level.
4. Enable documentation export that includes policy element details in addition to the diagram.

## 3. Non-Goals

1. No policy editing in UI (view-only remains intact).
2. No changes to dagre chain-compression behavior or core layout algorithm.
3. No collapse/expand rule-chain feature work.
4. No database or persistent server-side storage.
5. No cross-file policy comparison in this feature.

## 4. User Stories

1. As a network administrator, I can click a diagram node and see full rule details in a side inspector so I can understand exact match conditions and actions.
2. As an auditor, I can export a PDF that includes both the diagram and an appendix of policy element details for review records.
3. As an operator, I can trace inspector details back to stable rule identifiers (rule ID and node trace ID) for reproducible analysis.

## 5. UX Design Contract

### 5.1 Primary UI Surface

- A right-side inspector panel is the primary details surface.
- The panel is non-canvas UI and must not alter React Flow node measurement or dagre layout inputs.
- Inspector content is driven by current selected diagram node.

### 5.2 Interaction Behavior

- Node selection updates inspector content immediately.
- Empty state is shown when no node is selected.
- Structural-node fallback is shown for nodes without rule mapping (for example start/end nodes).
- Unresolved-reference state is shown when rule mapping cannot be completed.

### 5.3 Reader-Friendly Rendering

Inspector sections (v1):
1. Summary
2. Condition
3. Action
4. Flow Behavior
5. Linked References

Condition formatting requirements:
- Display Boolean grouping (AND/OR/NOT) clearly.
- Show predicate attribute/operator/value in readable lines.
- Preserve canonical meaning from normalized AST.

## 6. Data Contract

### 6.1 API Compatibility

- `POST /api/flow` remains backward-compatible by default.
- Policy details are included only when explicitly requested via optional flag.
- Existing clients that do not request details receive unchanged behavior.

### 6.2 Details Payload Scope

Details payload (v1) must support:
1. Service-level summary context.
2. Authentication/authen rule details.
3. Role-mapping/authz decision details.
4. Enforcement/profile action details.
5. Warning context for unresolved references.

### 6.3 Mapping Invariants

- `trace_rule_id` remains the primary bridge from diagram node to detailed rule object.
- Rule order in details payload must preserve policy evaluation order.
- If a `trace_rule_id` cannot resolve, inspector and export must display an explicit unresolved marker and retain available identifiers.

## 7. Export Contract (PDF Appendix v1)

### 7.1 Export Modes

PDF options:
1. Existing diagram-only mode (unchanged).
2. New diagram+appendix mode (additive).

### 7.2 Appendix Structure

Appendix sections (ordered):
1. Service Match Context
2. Authentication Rules
3. Role Mapping / Authorization Rules
4. Enforcement / Profile Application Rules
5. Warnings (if present)

Rows within each section must be ordered by stable policy rank/index.

### 7.3 Required Appendix Columns

1. Rule ID
2. Node Trace ID
3. Rule Name or Index
4. Condition (pretty text)
5. Action
6. Flow-on-match behavior
7. Linked object names (roles/profiles/stores as applicable)

### 7.4 Readability Requirements

- Consistent section headers and page headers.
- Wrapping behavior for long conditions.
- Clear visual separation between sections.
- Deterministic content ordering for repeat exports.

## 8. Acceptance Criteria

### 8.1 UX

1. Inspector appears as right-side panel and does not overlap or mutate diagram nodes.
2. Selecting nodes updates details content correctly.
3. Structural nodes show clear fallback content.
4. Inspector behavior remains compatible with existing annotation interactions.

### 8.2 Data and Compatibility

1. `/api/flow` default response shape remains unchanged when details are not requested.
2. Optional details response is available for both ClearPass and ISE files.
3. Details maintain stable rule ordering and identifier integrity.

### 8.3 Export

1. PDF diagram-only mode remains unchanged.
2. PDF diagram+appendix mode includes all required sections and columns.
3. Appendix rows cross-reference rule IDs and node trace IDs correctly.

### 8.4 Quality and Determinism

1. Existing test suites remain green.
2. New tests validate details payload, inspector mapping, and appendix completeness.
3. Deterministic output expectations are preserved.

## 9. Implementation Notes

### 9.1 Backend

- Add optional details inclusion path in API flow route.
- Add serialization helpers for ClearPass and ISE policy detail objects.
- Reuse canonical AST structures for readable condition rendering output.

### 9.2 Frontend

- Add `PolicyDetailsPanel` component.
- Wire selected node state to detail resolver using `trace_rule_id`.
- Keep inspector outside canvas layout computation path.

### 9.3 Export Pipeline

- Extend existing PDF export with appendix generation in additive mode.
- Generate table-like sections using stable ordered data from details payload.

## 10. Rollout Plan

1. Phase A: API optional details payload and serializers.
2. Phase B: Inspector UI integration and mapping logic.
3. Phase C: PDF appendix export mode and formatting.
4. Phase D: Test hardening and regression validation.

## 11. Risks and Mitigations

1. Large payload size for complex policies.
- Mitigation: optional details flag, possible lazy loading strategy.

2. Rule-resolution mismatch from `trace_rule_id` mapping edge cases.
- Mitigation: explicit unresolved marker paths and contract tests.

3. UI interference with diagram layout.
- Mitigation: enforce panel-outside-canvas architecture and non-measuring component boundary.

## 12. Test Plan

Fixture coverage:
1. `tests/fixtures/Service.xml`
2. `tests/fixtures/TacacsService.xml`
3. `tests/fixtures/ISEPolicyConfig.xml`

Required test coverage:
1. API compatibility tests for with/without details flag.
2. Serialization and ordering tests for both pipelines.
3. Inspector mapping tests from selected node to displayed details.
4. PDF appendix content tests for section presence, ordering, and key fields.

## 13. Open Questions

1. Should inspector default be open or collapsed on first diagram load?
2. Should appendix condition content be pretty text only or include optional full AST representation?
3. Should warnings always be a dedicated appendix section even when empty?
4. Should appendix include per-section counts (for example total auth rules, total enforcement rules)?
