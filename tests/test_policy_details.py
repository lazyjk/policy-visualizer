"""Tests for src/policy_details.py — detail serializers for both pipelines."""
from pathlib import Path

import pytest

from src.normalizer import And, Not, Op, Or, Predicate
from src.parser import parse
from src.policy_ir import build
from src.ise_parser import ise_parse
from src.ise_policy_ir import ise_build
from src.flow_ir import compile_service
from src.ise_flow_ir import ise_compile_policy_set
from src.policy_details import build_clearpass_details, build_ise_details, condition_to_text

CP_FIXTURE = Path(__file__).parent / "fixtures" / "Service.xml"
TACACS_FIXTURE = Path(__file__).parent / "fixtures" / "TacacsService.xml"
ISE_FIXTURE = Path(__file__).parent / "fixtures" / "ISEPolicyConfig.xml"


# ---------------------------------------------------------------------------
# condition_to_text
# ---------------------------------------------------------------------------

def test_condition_to_text_none():
    assert condition_to_text(None) == "(no condition)"


def test_condition_to_text_predicate():
    p = Predicate(
        namespace="Radius",
        attribute="NAS-IP-Address",
        op=Op.equals,
        rhs_raw="10.0.0.1",
        rhs_display="10.0.0.1",
    )
    text = condition_to_text(p)
    assert "Radius" in text
    assert "NAS-IP-Address" in text
    assert "10.0.0.1" in text


def test_condition_to_text_and():
    p1 = Predicate("A", "x", Op.equals, "1", "1")
    p2 = Predicate("B", "y", Op.equals, "2", "2")
    text = condition_to_text(And(operands=[p1, p2]))
    assert "AND" in text


def test_condition_to_text_or():
    p1 = Predicate("A", "x", Op.equals, "1", "1")
    p2 = Predicate("B", "y", Op.equals, "2", "2")
    text = condition_to_text(Or(operands=[p1, p2]))
    assert "OR" in text


def test_condition_to_text_not():
    p = Predicate("A", "x", Op.equals, "1", "1")
    text = condition_to_text(Not(operand=p))
    assert "NOT" in text


# ---------------------------------------------------------------------------
# build_clearpass_details — ClearPass fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cp_details():
    raw = parse(CP_FIXTURE)
    ir = build(raw)
    svc = next(iter(ir.services.values()))
    return build_clearpass_details(svc, ir), svc, ir


def test_clearpass_service_context_fields(cp_details):
    details, svc, _ = cp_details
    ctx = details["service_context"]
    assert ctx["service_name"] == svc.name
    assert ctx["service_type"] == svc.service_type
    assert "condition_text" in ctx


def test_clearpass_authen_rules_empty(cp_details):
    details, _, _ = cp_details
    assert details["authen_rules"] == []


def test_clearpass_role_mapping_rules_ordered(cp_details):
    details, _, _ = cp_details
    rules = details["role_mapping_rules"]
    if rules:
        indices = [r["index"] for r in rules]
        assert indices == sorted(indices)


def test_clearpass_enforcement_rules_ordered(cp_details):
    details, _, _ = cp_details
    rules = details["enforcement_rules"]
    if rules:
        indices = [r["index"] for r in rules]
        assert indices == sorted(indices)


def test_clearpass_action_text_set_role(cp_details):
    details, _, _ = cp_details
    for rule in details["role_mapping_rules"]:
        assert "Set Role:" in rule["action_text"]


def test_clearpass_action_text_apply_profiles(cp_details):
    details, _, _ = cp_details
    for rule in details["enforcement_rules"]:
        # action_text is profile names joined with ", " or "(no profiles)"
        assert isinstance(rule["action_text"], str)
        assert len(rule["action_text"]) > 0


def test_clearpass_rule_index_keys_present(cp_details):
    details, svc, ir = cp_details
    flow = compile_service(svc, ir)
    trace_ids = {n.trace_rule_id for n in flow.nodes if n.trace_rule_id}
    rule_index_keys = set(details["rule_index"].keys())
    assert rule_index_keys.issubset(trace_ids)


def test_clearpass_rule_index_nonempty(cp_details):
    details, _, _ = cp_details
    # Should have entries from role_mapping or enforcement rules
    assert len(details["rule_index"]) > 0


def test_clearpass_warnings_list(cp_details):
    details, _, _ = cp_details
    assert isinstance(details["warnings"], list)


def test_clearpass_on_match_values(cp_details):
    details, _, _ = cp_details
    for rule in details["role_mapping_rules"] + details["enforcement_rules"]:
        assert rule["on_match"] in ("stop", "continue")


def test_clearpass_rule_name_is_policy_name(cp_details):
    """Rule name field must carry the parent policy's human-readable name."""
    details, svc, ir = cp_details
    rm_policy = ir.role_mapping_policies.get(svc.role_mapping_policy_id)
    if rm_policy and details["role_mapping_rules"]:
        for rule in details["role_mapping_rules"]:
            assert rule["name"] == rm_policy.name

    enf_policy = ir.enforcement_policies.get(svc.enforcement_policy_id)
    if enf_policy and details["enforcement_rules"]:
        for rule in details["enforcement_rules"]:
            assert rule["name"] == enf_policy.name


# ---------------------------------------------------------------------------
# build_clearpass_details — TACACS fixture
# ---------------------------------------------------------------------------

def test_tacacs_details_service_type():
    raw = parse(TACACS_FIXTURE)
    ir = build(raw)
    svc = next(iter(ir.services.values()))
    details = build_clearpass_details(svc, ir)
    assert details["service_context"]["service_type"] == "TACACS"


# ---------------------------------------------------------------------------
# build_ise_details — ISE fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ise_details():
    raw = ise_parse(ISE_FIXTURE)
    ir = ise_build(raw)
    ps = ir.policy_sets[0]
    return build_ise_details(ps, ir), ps, ir


def test_ise_service_context_fields(ise_details):
    details, ps, _ = ise_details
    ctx = details["service_context"]
    assert ctx["service_name"] == ps.name
    assert ctx["service_type"] == ps.set_type
    assert "condition_text" in ctx


def test_ise_role_mapping_rules_empty(ise_details):
    details, _, _ = ise_details
    assert details["role_mapping_rules"] == []


def test_ise_authen_rules_ordered(ise_details):
    details, _, _ = ise_details
    rules = details["authen_rules"]
    if rules:
        indices = [r["index"] for r in rules]
        assert indices == sorted(indices)


def test_ise_enforcement_rules_ordered(ise_details):
    details, _, _ = ise_details
    rules = details["enforcement_rules"]
    if rules:
        indices = [r["index"] for r in rules]
        assert indices == sorted(indices)


def test_ise_authen_action_text(ise_details):
    details, _, _ = ise_details
    for rule in details["authen_rules"]:
        assert "Auth:" in rule["action_text"]


def test_ise_author_action_text(ise_details):
    details, _, _ = ise_details
    for rule in details["enforcement_rules"]:
        assert isinstance(rule["action_text"], str)
        assert len(rule["action_text"]) > 0


def test_ise_rule_index_keys_present(ise_details):
    details, ps, ir = ise_details
    flow = ise_compile_policy_set(ps, ir)
    trace_ids = {n.trace_rule_id for n in flow.nodes if n.trace_rule_id}
    rule_index_keys = set(details["rule_index"].keys())
    assert rule_index_keys.issubset(trace_ids)


def test_ise_rule_index_nonempty(ise_details):
    details, _, _ = ise_details
    assert len(details["rule_index"]) > 0


def test_ise_on_match_continue(ise_details):
    details, _, _ = ise_details
    # Authen rules with user_not_found_action=CONTINUE should have on_match="continue"
    raw = ise_parse(ISE_FIXTURE)
    ir = ise_build(raw)
    ps = ir.policy_sets[0]
    for rule in ps.authen_rules:
        d = next((r for r in details["authen_rules"] if r["rule_id"] == rule.id), None)
        if d and rule.user_not_found_action == "CONTINUE":
            assert d["on_match"] == "continue"


def test_ise_warnings_list(ise_details):
    details, _, _ = ise_details
    assert isinstance(details["warnings"], list)


# ---------------------------------------------------------------------------
# evaluate-all on_match propagation
# ---------------------------------------------------------------------------

EVAL_ALL_FIXTURE = Path(__file__).parent / "fixtures" / "EvaluateAll.xml"


def test_eval_all_enf_rules_on_match_continue():
    raw = parse(EVAL_ALL_FIXTURE)
    ir = build(raw, source_file=str(EVAL_ALL_FIXTURE))
    ep = next(iter(ir.enforcement_policies.values()))
    assert ep.rule_combine_algo == "evaluate-all"
    for rule in ep.rules:
        assert rule.flow.on_match == "continue"


def test_eval_all_rm_rules_on_match_continue():
    raw = parse(EVAL_ALL_FIXTURE)
    ir = build(raw, source_file=str(EVAL_ALL_FIXTURE))
    rm = next(iter(ir.role_mapping_policies.values()))
    assert rm.rule_combine_algo == "evaluate-all"
    for rule in rm.rules:
        assert rule.flow.on_match == "continue"


def test_first_applicable_enf_rules_on_match_stop():
    raw = parse(CP_FIXTURE)
    ir = build(raw, source_file=str(CP_FIXTURE))
    first_applicable_eps = [ep for ep in ir.enforcement_policies.values() if ep.rule_combine_algo == "first-applicable"]
    assert first_applicable_eps, "Expected at least one first-applicable enforcement policy in fixture"
    for ep in first_applicable_eps:
        for rule in ep.rules:
            assert rule.flow.on_match == "stop"


# ---------------------------------------------------------------------------
# Tier 1: profiles, enforcement default, service settings
# ---------------------------------------------------------------------------

ATTR_FIXTURE = Path(__file__).parent / "fixtures" / "ProfileAttributes.xml"


@pytest.fixture(scope="module")
def attr_ctx():
    ir = build(parse(ATTR_FIXTURE), source_file=str(ATTR_FIXTURE))
    svc = next(s for s in ir.services.values() if s.name == "corp-wireless")
    return svc, ir, build_clearpass_details(svc, ir), compile_service(svc, ir)


def test_enforcement_rule_profiles_with_attributes(attr_ctx):
    _, _, details, _ = attr_ctx
    rule0 = details["enforcement_rules"][0]
    assert [p["name"] for p in rule0["profiles"]] == ["corp-staff-access"]
    attrs = rule0["profiles"][0]["attributes"]
    assert attrs[0] == {
        "name": "Aruba-User-Role", "type": "Radius:Aruba",
        "value": "staff-role", "display_value": "staff-role",
    }
    # Multi-profile rule keeps rule order
    rule1 = details["enforcement_rules"][1]
    assert [p["name"] for p in rule1["profiles"]] == ["contractor-vlan", "contractor-role"]
    # Back-compat fields unchanged
    assert rule1["action_text"] == "contractor-vlan, contractor-role"


def test_role_mapping_rules_have_empty_profiles(attr_ctx):
    _, _, details, _ = attr_ctx
    assert all(r["profiles"] == [] for r in details["role_mapping_rules"])


def test_enforcement_default_entry(attr_ctx):
    _, _, details, flow = attr_ctx
    default = details["enforcement_default"]
    assert default is not None
    assert default["name"] == "Default"
    assert default["profiles"][0]["name"] == "corp-guest-default"
    assert details["rule_index"][default["node_trace_id"]] is default
    default_node = next(n for n in flow.nodes if n.id.endswith("__enf_default_action"))
    assert default_node.trace_rule_id == default["node_trace_id"]


def test_rule_index_keys_still_subset_of_trace_ids(attr_ctx):
    _, _, details, flow = attr_ctx
    trace_ids = {n.trace_rule_id for n in flow.nodes if n.trace_rule_id}
    assert set(details["rule_index"]).issubset(trace_ids)


def test_service_context_settings(attr_ctx):
    _, _, details, _ = attr_ctx
    ctx = details["service_context"]
    assert ctx["enabled"] is True
    assert ctx["template"] == "IBNS_WIRELESS"
    assert ctx["use_cached_results"] is True
    assert ctx["monitor_mode"] is False
    assert ctx["role_mapping_policy_name"] == "corp-rm"
    assert ctx["enforcement_policy_name"] == "corp-enf"


def test_ise_details_new_fields_default():
    ir = ise_build(ise_parse(ISE_FIXTURE), source_file=str(ISE_FIXTURE))
    details = build_ise_details(ir.policy_sets[0], ir)
    assert details.get("enforcement_default") is None
    assert all(r.get("profiles", []) == [] for r in details["enforcement_rules"])
