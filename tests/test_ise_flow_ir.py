"""Tests for ISE Flow IR Compiler (src/ise_flow_ir.py)."""
import pytest

from src.ise_flow_ir import ise_compile_policy_set
from src.ise_policy_ir import ISEAuthenRule, ISEAuthorRule, ISEPolicyIR, ISEPolicySet, ISEProfile
from src.normalizer import And, Op, Predicate


# ---------------------------------------------------------------------------
# Helpers — minimal in-memory ISE objects
# ---------------------------------------------------------------------------

def _predicate(attr="Protocol", ns="Radius", op=Op.equals, rhs="Dot1X"):
    return Predicate(namespace=ns, attribute=attr, op=op, rhs_raw=rhs, rhs_display=rhs)


def _authen_rule(name="Auth", idx=0, when=None, storename="AD", storetype="IdentityStore",
                 fail="REJECT", unf="REJECT"):
    return ISEAuthenRule(
        id=f"authen-{idx}",
        name=name,
        index=idx,
        when=when,
        storetype=storetype,
        storename=storename,
        authen_fail_action=fail,
        user_not_found_action=unf,
    )


def _author_rule(name="Allow", idx=0, when=None, profiles=None, commandsets=None, security_groups=None):
    return ISEAuthorRule(
        id=f"author-{idx}",
        name=name,
        index=idx,
        when=when,
        profile_names=profiles or ["PermitAccess"],
        commandset_names=commandsets or [],
        security_groups=security_groups or [],
    )


def _ir(policy_set, extra_profiles=None):
    ir = ISEPolicyIR()
    ir.profiles["PermitAccess"] = ISEProfile(
        name="PermitAccess", profile_type="standard", access_type="ACCESS_ACCEPT"
    )
    ir.profiles["DenyAccess"] = ISEProfile(
        name="DenyAccess", profile_type="standard", access_type="ACCESS_REJECT"
    )
    if extra_profiles:
        ir.profiles.update(extra_profiles)
    ir.policy_sets.append(policy_set)
    return ir


def _ps(match=None, authen_rules=None, author_rules=None, set_type="RADIUS"):
    return ISEPolicySet(
        id="ps1",
        name="Test-PS",
        description="",
        rank=0,
        set_type=set_type,
        allowed_protocols="Default Network Access",
        match=match,
        authen_rules=authen_rules or [],
        author_rules=author_rules or [],
    )


# ---------------------------------------------------------------------------
# Basic graph structure
# ---------------------------------------------------------------------------

def test_start_node_present():
    ps = _ps(authen_rules=[_authen_rule()], author_rules=[_author_rule()])
    flow = ise_compile_policy_set(ps, _ir(ps))
    ids = {n.id for n in flow.nodes}
    assert "ps1__start" in ids


def test_start_node_type():
    ps = _ps(authen_rules=[_authen_rule()], author_rules=[_author_rule()])
    flow = ise_compile_policy_set(ps, _ir(ps))
    start = next(n for n in flow.nodes if n.id == "ps1__start")
    assert start.type == "start"


def test_flow_has_expected_node_types():
    ps = _ps(
        match=_predicate(),
        authen_rules=[_authen_rule(when=_predicate())],
        author_rules=[_author_rule(when=_predicate())],
    )
    flow = ise_compile_policy_set(ps, _ir(ps))
    types = {n.type for n in flow.nodes}
    assert "start" in types
    assert "decision" in types
    assert "process" in types
    assert "action" in types
    assert "end" in types


# ---------------------------------------------------------------------------
# Match condition (policy set level)
# ---------------------------------------------------------------------------

def test_match_all_skips_match_decision():
    """match=None → no policy-set-level decision node."""
    ps = _ps(authen_rules=[_authen_rule()], author_rules=[_author_rule()])
    flow = ise_compile_policy_set(ps, _ir(ps))
    ids = {n.id for n in flow.nodes}
    assert "ps1__match" not in ids


def test_match_condition_creates_decision_node():
    ps = _ps(match=_predicate(), authen_rules=[_authen_rule()], author_rules=[_author_rule()])
    flow = ise_compile_policy_set(ps, _ir(ps))
    ids = {n.id for n in flow.nodes}
    assert "ps1__match" in ids


def test_match_decision_has_no_edge():
    """When match=None, start connects directly to authen entry (not a match decision)."""
    ps = _ps(authen_rules=[_authen_rule()], author_rules=[_author_rule()])
    flow = ise_compile_policy_set(ps, _ir(ps))
    start_edges = [e for e in flow.edges if e.from_id == "ps1__start"]
    assert len(start_edges) == 1
    assert start_edges[0].to_id != "ps1__match"


def test_match_decision_yes_no_edges():
    ps = _ps(match=_predicate(), authen_rules=[_authen_rule()], author_rules=[_author_rule()])
    flow = ise_compile_policy_set(ps, _ir(ps))
    match_edges = {e.label for e in flow.edges if e.from_id == "ps1__match"}
    assert "YES" in match_edges
    assert "NO" in match_edges


# ---------------------------------------------------------------------------
# Authen chain edge labels
# ---------------------------------------------------------------------------

def test_authen_process_has_pass_and_fail_edges():
    ps = _ps(authen_rules=[_authen_rule()], author_rules=[_author_rule()])
    flow = ise_compile_policy_set(ps, _ir(ps))
    proc_id = "ps1__authen_proc_0"
    labels = {e.label for e in flow.edges if e.from_id == proc_id}
    assert "PASS" in labels
    assert "FAIL" in labels


def test_authen_continue_edge_when_unf_continue():
    ps = _ps(
        authen_rules=[
            _authen_rule(idx=0, unf="CONTINUE"),
            _authen_rule(name="Auth2", idx=1),
        ],
        author_rules=[_author_rule()],
    )
    flow = ise_compile_policy_set(ps, _ir(ps))
    proc0_labels = {e.label for e in flow.edges if e.from_id == "ps1__authen_proc_0"}
    assert "CONTINUE" in proc0_labels


def test_authen_no_continue_edge_when_unf_reject():
    ps = _ps(authen_rules=[_authen_rule(unf="REJECT")], author_rules=[_author_rule()])
    flow = ise_compile_policy_set(ps, _ir(ps))
    proc0_labels = {e.label for e in flow.edges if e.from_id == "ps1__authen_proc_0"}
    assert "CONTINUE" not in proc0_labels


# ---------------------------------------------------------------------------
# Authz chain
# ---------------------------------------------------------------------------

def test_authz_allow_end_label():
    ps = _ps(authen_rules=[_authen_rule()], author_rules=[_author_rule(profiles=["PermitAccess"])])
    flow = ise_compile_policy_set(ps, _ir(ps))
    end_nodes = [n for n in flow.nodes if n.type == "end"]
    labels = {n.label for n in end_nodes}
    assert any("ALLOW" in l for l in labels)


def test_authz_deny_end_label():
    ps = _ps(authen_rules=[_authen_rule()], author_rules=[_author_rule(profiles=["DenyAccess"])])
    flow = ise_compile_policy_set(ps, _ir(ps))
    end_nodes = [n for n in flow.nodes if n.type == "end"]
    labels = {n.label for n in end_nodes}
    assert any("DENY" in l for l in labels)


def test_authz_implicit_deny_when_last_rule_has_condition():
    """When last authz rule has a condition, an implicit deny end is added for the NO path."""
    ps = _ps(
        authen_rules=[_authen_rule()],
        author_rules=[_author_rule(when=_predicate())],
    )
    flow = ise_compile_policy_set(ps, _ir(ps))
    ids = {n.id for n in flow.nodes}
    assert "ps1__authz_implicit_deny" in ids


# ---------------------------------------------------------------------------
# rank_group labels
# ---------------------------------------------------------------------------

def test_authen_decision_rank_group():
    ps = _ps(
        authen_rules=[_authen_rule(when=_predicate())],
        author_rules=[_author_rule()],
    )
    flow = ise_compile_policy_set(ps, _ir(ps))
    dec = next(n for n in flow.nodes if n.id == "ps1__authen_dec_0")
    assert dec.rank_group == "authen_chain"


def test_authz_decision_rank_group():
    ps = _ps(
        authen_rules=[_authen_rule()],
        author_rules=[_author_rule(when=_predicate())],
    )
    flow = ise_compile_policy_set(ps, _ir(ps))
    dec = next(n for n in flow.nodes if n.id == "ps1__authz_dec_0")
    assert dec.rank_group == "enf_chain"


# ---------------------------------------------------------------------------
# No rules edge cases
# ---------------------------------------------------------------------------

def test_no_authen_rules_produces_deny_end():
    ps = _ps(author_rules=[_author_rule()])
    flow = ise_compile_policy_set(ps, _ir(ps))
    end_labels = {n.label for n in flow.nodes if n.type == "end"}
    assert any("DENY" in l for l in end_labels)


def test_no_author_rules_produces_deny_end():
    ps = _ps(authen_rules=[_authen_rule()])
    flow = ise_compile_policy_set(ps, _ir(ps))
    end_labels = {n.label for n in flow.nodes if n.type == "end"}
    assert any("DENY" in l for l in end_labels)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_determinism():
    """Same input must produce identical node IDs and edge structure."""
    ps1 = _ps(match=_predicate(), authen_rules=[_authen_rule()], author_rules=[_author_rule()])
    ps2 = _ps(match=_predicate(), authen_rules=[_authen_rule()], author_rules=[_author_rule()])
    flow1 = ise_compile_policy_set(ps1, _ir(ps1))
    flow2 = ise_compile_policy_set(ps2, _ir(ps2))
    assert [n.id for n in flow1.nodes] == [n.id for n in flow2.nodes]
    assert [(e.from_id, e.to_id, e.label) for e in flow1.edges] == \
           [(e.from_id, e.to_id, e.label) for e in flow2.edges]


# ---------------------------------------------------------------------------
# TACACS service type
# ---------------------------------------------------------------------------

def test_tacacs_service_type_preserved():
    ps = _ps(
        authen_rules=[_authen_rule()],
        author_rules=[_author_rule()],
        set_type="TACACS",
    )
    flow = ise_compile_policy_set(ps, _ir(ps))
    assert flow.service_type == "TACACS"


# ---------------------------------------------------------------------------
# Security Groups
# ---------------------------------------------------------------------------

def test_security_group_appears_in_action_label():
    """action node label includes 'Security Group: <name>' when groups are set."""
    ps = _ps(
        authen_rules=[_authen_rule()],
        author_rules=[_author_rule(security_groups=["BYOD"])],
    )
    flow = ise_compile_policy_set(ps, _ir(ps))
    action = next(n for n in flow.nodes if n.type == "action")
    assert "Security Group: BYOD" in action.label


def test_no_security_group_no_label():
    """action node label does not contain 'Security Group' when groups is empty."""
    ps = _ps(
        authen_rules=[_authen_rule()],
        author_rules=[_author_rule(security_groups=[])],
    )
    flow = ise_compile_policy_set(ps, _ir(ps))
    action = next(n for n in flow.nodes if n.type == "action")
    assert "Security Group" not in action.label


def test_multiple_security_groups_all_appear():
    """Multiple security groups each appear on their own line."""
    ps = _ps(
        authen_rules=[_authen_rule()],
        author_rules=[_author_rule(security_groups=["Employees", "Contractors"])],
    )
    flow = ise_compile_policy_set(ps, _ir(ps))
    action = next(n for n in flow.nodes if n.type == "action")
    assert "Security Group: Employees" in action.label
    assert "Security Group: Contractors" in action.label
