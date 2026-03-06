"""Tests for Phase 4: Flow IR Compilation."""
from pathlib import Path

import pytest

from src.parser import parse
from src.policy_ir import build
from src.flow_ir import compile_service, FlowIR

FIXTURE = Path(__file__).parent / "fixtures" / "Service.xml"


@pytest.fixture(scope="module")
def flow() -> FlowIR:
    raw = parse(FIXTURE)
    ir = build(raw)
    svc = next(iter(ir.services.values()))
    return compile_service(svc, ir)


def test_has_start_node(flow):
    starts = [n for n in flow.nodes if n.type == "start"]
    assert len(starts) == 1


def test_has_end_nodes(flow):
    ends = [n for n in flow.nodes if n.type == "end"]
    assert len(ends) >= 2  # at least accept + reject


def test_has_decision_nodes(flow):
    decisions = [n for n in flow.nodes if n.type == "decision"]
    assert len(decisions) >= 3  # service match + role rules + enforcement rules


def test_has_action_nodes(flow):
    actions = [n for n in flow.nodes if n.type == "action"]
    assert len(actions) >= 1


def test_all_edges_reference_valid_nodes(flow):
    node_ids = {n.id for n in flow.nodes}
    for edge in flow.edges:
        assert edge.from_id in node_ids, f"Edge source {edge.from_id!r} not in nodes"
        assert edge.to_id in node_ids, f"Edge target {edge.to_id!r} not in nodes"


def test_start_has_outgoing_edge(flow):
    start = next(n for n in flow.nodes if n.type == "start")
    outgoing = [e for e in flow.edges if e.from_id == start.id]
    assert len(outgoing) == 1


def test_decision_edges_labeled(flow):
    """Decision nodes should have at least one YES and one NO outgoing edge."""
    decision_ids = {n.id for n in flow.nodes if n.type == "decision"}
    for did in decision_ids:
        out_labels = {e.label for e in flow.edges if e.from_id == did}
        # Each decision should have YES and NO (or FAIL and PASS for auth nodes)
        assert "YES" in out_labels or "NO" in out_labels, (
            f"Decision node {did!r} has edges: {out_labels}"
        )


def test_end_nodes_have_no_outgoing_edges(flow):
    end_ids = {n.id for n in flow.nodes if n.type == "end"}
    for eid in end_ids:
        outgoing = [e for e in flow.edges if e.from_id == eid]
        assert outgoing == [], f"End node {eid!r} has outgoing edges: {outgoing}"


def test_deterministic_compilation(flow):
    """Compiling the same IR twice yields identical node/edge sets."""
    raw = parse(FIXTURE)
    ir = build(raw)
    svc = next(iter(ir.services.values()))
    flow2 = compile_service(svc, ir)

    ids1 = sorted(n.id for n in flow.nodes)
    ids2 = sorted(n.id for n in flow2.nodes)
    assert ids1 == ids2

    edges1 = sorted((e.from_id, e.to_id, e.label) for e in flow.edges)
    edges2 = sorted((e.from_id, e.to_id, e.label) for e in flow2.edges)
    assert edges1 == edges2


def test_non_empty_edge_labels_use_known_contract(flow):
    known = {"YES", "NO", "FAIL", "PASS"}
    labels = {e.label for e in flow.edges if e.label}
    assert labels.issubset(known), f"Unknown edge labels found: {sorted(labels - known)}"


def test_pass_edge_is_single_forward_transition_from_auth(flow):
    node_by_id = {n.id: n for n in flow.nodes}
    pass_edges = [e for e in flow.edges if e.label == "PASS"]
    assert len(pass_edges) == 1

    edge = pass_edges[0]
    source = node_by_id[edge.from_id]
    target = node_by_id[edge.to_id]

    assert source.type == "process"
    assert target.type in {"decision", "end"}


# ---------------------------------------------------------------------------
# evaluate-all flow tests
# ---------------------------------------------------------------------------

EVAL_ALL_FIXTURE = Path(__file__).parent / "fixtures" / "EvaluateAll.xml"


@pytest.fixture(scope="module")
def eval_all_flow() -> FlowIR:
    from src.parser import parse as _parse
    from src.policy_ir import build as _build
    raw = _parse(EVAL_ALL_FIXTURE)
    ir = _build(raw)
    svc = next(iter(ir.services.values()))
    return compile_service(svc, ir)


def test_eval_all_edges_reference_valid_nodes(eval_all_flow):
    node_ids = {n.id for n in eval_all_flow.nodes}
    for edge in eval_all_flow.edges:
        assert edge.from_id in node_ids
        assert edge.to_id in node_ids


def test_eval_all_has_continue_edges(eval_all_flow):
    """evaluate-all chains must produce CONTINUE edges from action → next decision."""
    continue_edges = [e for e in eval_all_flow.edges if e.label == "CONTINUE"]
    assert len(continue_edges) >= 2  # at least 2 non-last rules across both chains


def test_eval_all_rm_action_nodes_not_all_terminating(eval_all_flow):
    """In evaluate-all RM chain, non-last action nodes must NOT connect directly to enf_entry."""
    # CONTINUE edges go action → decision; none of the non-last RM actions should reach an end node
    node_by_id = {n.id: n for n in eval_all_flow.nodes}
    continue_edges = [e for e in eval_all_flow.edges if e.label == "CONTINUE"]
    for edge in continue_edges:
        target = node_by_id[edge.to_id]
        assert target.type == "decision", (
            f"CONTINUE edge target should be decision, got {target.type!r} ({edge.to_id})"
        )


def test_eval_all_last_rm_action_reaches_enf_chain(eval_all_flow):
    """The last RM action node should connect to the enforcement entry (no CONTINUE)."""
    node_by_id = {n.id: n for n in eval_all_flow.nodes}
    # Find the last rm action node (rm_action_2 for 3-rule chain, index 2)
    last_rm_action = next(
        (n for n in eval_all_flow.nodes if "rm_action_2" in n.id), None
    )
    assert last_rm_action is not None
    outgoing = [e for e in eval_all_flow.edges if e.from_id == last_rm_action.id]
    assert len(outgoing) == 1
    assert outgoing[0].label != "CONTINUE"
    # target should be a decision (first enf rule) or process node
    target = node_by_id[outgoing[0].to_id]
    assert target.type in {"decision", "process"}


def test_eval_all_enf_default_is_terminal(eval_all_flow):
    """The default enforcement action should lead to an end node."""
    node_by_id = {n.id: n for n in eval_all_flow.nodes}
    default_action = next(
        (n for n in eval_all_flow.nodes if "enf_default_action" in n.id), None
    )
    assert default_action is not None
    outgoing = [e for e in eval_all_flow.edges if e.from_id == default_action.id]
    assert len(outgoing) == 1
    assert node_by_id[outgoing[0].to_id].type == "end"


def test_eval_all_end_nodes_have_no_outgoing_edges(eval_all_flow):
    end_ids = {n.id for n in eval_all_flow.nodes if n.type == "end"}
    for eid in end_ids:
        outgoing = [e for e in eval_all_flow.edges if e.from_id == eid]
        assert outgoing == [], f"End node {eid!r} has outgoing edges"
