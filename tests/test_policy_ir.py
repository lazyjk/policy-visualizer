"""Tests for Phase 3: Policy IR Construction."""
from pathlib import Path

import pytest

from src.parser import parse
from src.policy_ir import build, SetRole, ApplyProfiles

FIXTURE = Path(__file__).parent / "fixtures" / "Service.xml"


@pytest.fixture(scope="module")
def ir():
    raw = parse(FIXTURE)
    return build(raw, source_file=str(FIXTURE))


def test_service_present(ir):
    assert len(ir.services) == 1


def test_service_has_match(ir):
    svc = next(iter(ir.services.values()))
    assert svc.match is not None


def test_service_links_role_mapping(ir):
    svc = next(iter(ir.services.values()))
    assert svc.role_mapping_policy_name == "Secure Role Mapping (Enforcement)"
    assert svc.role_mapping_policy_id in ir.role_mapping_policies


def test_service_links_enforcement_policy(ir):
    svc = next(iter(ir.services.values()))
    assert svc.enforcement_policy_name == "Secure User Enforcement Policy"
    assert svc.enforcement_policy_id in ir.enforcement_policies


def test_role_mapping_rule_count(ir):
    rm = next(iter(ir.role_mapping_policies.values()))
    assert len(rm.rules) == 17


def test_rule_ordering_preserved(ir):
    rm = next(iter(ir.role_mapping_policies.values()))
    indices = [r.index for r in rm.rules]
    assert indices == sorted(indices)


def test_role_mapping_default(ir):
    rm = next(iter(ir.role_mapping_policies.values()))
    assert rm.default is not None
    assert isinstance(rm.default, SetRole)
    assert rm.default.role_name == "WirelessDenied"


def test_enforcement_policy_rules(ir):
    ep = next(iter(ir.enforcement_policies.values()))
    assert len(ep.rules) == 5
    for rule in ep.rules:
        assert isinstance(rule.then, ApplyProfiles)


def test_enforcement_default_is_deny(ir):
    ep = next(iter(ir.enforcement_policies.values()))
    assert ep.default is not None
    assert isinstance(ep.default, ApplyProfiles)
    deny_names = [n for n in ep.default.profile_names if "deny" in n.lower()]
    assert len(deny_names) > 0


def test_deterministic_ids(ir):
    """Same name must always produce the same ID."""
    raw = parse(FIXTURE)
    ir2 = build(raw, source_file=str(FIXTURE))
    assert set(ir.services.keys()) == set(ir2.services.keys())
    assert set(ir.role_mapping_policies.keys()) == set(ir2.role_mapping_policies.keys())
    assert set(ir.enforcement_policies.keys()) == set(ir2.enforcement_policies.keys())


def test_roles_populated(ir):
    role_names = {r.name for r in ir.roles.values()}
    assert "Students" in role_names
    assert "Faculty-Staff" in role_names
    assert "Blacklisted" in role_names


# ---------------------------------------------------------------------------
# Fail-fast reference validation
# ---------------------------------------------------------------------------

def _minimal_raw(**overrides) -> dict:
    """Return the smallest valid raw dict, with optional field overrides."""
    base = {
        "roles": [],
        "authMethods": [],
        "authSources": [],
        "radiusEnfProfiles": [],
        "postAuthEnfProfiles": [],
        "tacacsEnfProfiles": [],
        "roleMappings": [],
        "enforcementPolicies": [],
        "services": [],
    }
    base.update(overrides)
    return base


def test_unresolved_enforcement_profile_creates_placeholder():
    raw = _minimal_raw(
        enforcementPolicies=[{
            "name": "TestPolicy",
            "policyType": "RADIUS",
            "rules": [{
                "index": 1,
                "expression": None,
                "results": [{"name": "Enforcement-Profile", "displayValue": "GhostProfile"}],
            }],
        }]
    )
    ir = build(raw)
    profiles = {p.name for p in ir.enforcement_profiles.values()}
    assert "GhostProfile" in profiles


def test_unresolved_role_in_rule_creates_placeholder():
    raw = _minimal_raw(
        roleMappings=[{
            "name": "TestRM",
            "ruleCombineAlgo": "first-applicable",
            "rules": [{
                "index": 1,
                "expression": None,
                "results": [{"name": "Role", "displayValue": "GhostRole"}],
            }],
            "defaultRole": "",
        }]
    )
    ir = build(raw)
    roles = {r.name for r in ir.roles.values()}
    assert "GhostRole" in roles


def test_unresolved_default_role_creates_placeholder():
    raw = _minimal_raw(
        roleMappings=[{
            "name": "TestRM",
            "ruleCombineAlgo": "first-applicable",
            "rules": [],
            "defaultRole": "NonExistentRole",
        }]
    )
    ir = build(raw)
    roles = {r.name for r in ir.roles.values()}
    assert "NonExistentRole" in roles


def test_multiple_unresolved_profiles_all_created():
    """All unresolved profile names should become placeholder entries."""
    raw = _minimal_raw(
        enforcementPolicies=[{
            "name": "TestPolicy",
            "policyType": "RADIUS",
            "rules": [{
                "index": 1,
                "expression": None,
                "results": [{"name": "Enforcement-Profile", "displayValue": "Alpha, Beta"}],
            }],
        }]
    )
    ir = build(raw)
    profiles = {p.name for p in ir.enforcement_profiles.values()}
    assert "Alpha" in profiles
    assert "Beta" in profiles


# ---------------------------------------------------------------------------
# evaluate-all algorithm tests
# ---------------------------------------------------------------------------

EVAL_ALL_FIXTURE = Path(__file__).parent / "fixtures" / "EvaluateAll.xml"


@pytest.fixture(scope="module")
def eval_all_ir():
    raw = parse(EVAL_ALL_FIXTURE)
    return build(raw, source_file=str(EVAL_ALL_FIXTURE))


def test_eval_all_rm_rule_combine_algo(eval_all_ir):
    rm = next(iter(eval_all_ir.role_mapping_policies.values()))
    assert rm.rule_combine_algo == "evaluate-all"


def test_eval_all_enf_rule_combine_algo(eval_all_ir):
    ep = next(iter(eval_all_ir.enforcement_policies.values()))
    assert ep.rule_combine_algo == "evaluate-all"


def test_first_applicable_enf_default_algo(ir):
    """Existing fixture enforcement policy should default to first-applicable."""
    ep = next(iter(ir.enforcement_policies.values()))
    assert ep.rule_combine_algo == "first-applicable"


def test_eval_all_rm_has_three_rules(eval_all_ir):
    rm = next(iter(eval_all_ir.role_mapping_policies.values()))
    assert len(rm.rules) == 3


def test_eval_all_enf_has_two_rules(eval_all_ir):
    ep = next(iter(eval_all_ir.enforcement_policies.values()))
    assert len(ep.rules) == 2


# ---------------------------------------------------------------------------
# TACACS enforcement profile classification
# ---------------------------------------------------------------------------

TACACS_FIXTURE = Path(__file__).parent / "fixtures" / "TacacsService.xml"


@pytest.fixture(scope="module")
def tacacs_ir():
    from src.parser import parse as _parse
    raw = _parse(TACACS_FIXTURE)
    return build(raw)


def test_tacacs_priv15_is_accept(tacacs_ir):
    profiles = {p.name: p for p in tacacs_ir.enforcement_profiles.values()}
    p = profiles["TACACS Cisco Priv 15"]
    assert p.profile_type == "tacacs_accept"
    assert p.metadata.get("tacacs_priv_level") == "15"


def test_tacacs_priv0_is_deny(tacacs_ir):
    profiles = {p.name: p for p in tacacs_ir.enforcement_profiles.values()}
    p = profiles["[TACACS+ Deny Profile]"]
    assert p.profile_type == "tacacs_deny"
    assert p.metadata.get("tacacs_priv_level") == "0"


@pytest.mark.parametrize("action,autz,priv,expected_type", [
    ("Accept", "PASS_ADD", "15", "tacacs_accept"),
    ("Accept", "PASS_ADD", "0",  "tacacs_deny"),   # effective deny via Priv 0
    ("",       "FAIL",     "",   "tacacs_deny"),   # explicit FAIL status
    ("Reject", "PASS_ADD", "",   "tacacs_deny"),   # non-accept action
    ("Accept", "PASS_ADD", "",   "tacacs_accept"),  # plain accept, no priv level
])
def test_tacacs_profile_type_classification(action, autz, priv, expected_type):
    raw = _minimal_raw(tacacsEnfProfiles=[{
        "name": "TestTACACS",
        "description": "",
        "action": action,
        "autzStatus": autz,
        "maxPrivLevel": priv,
    }])
    ir = build(raw)
    profiles = {p.name: p for p in ir.enforcement_profiles.values()}
    assert profiles["TestTACACS"].profile_type == expected_type


# ---------------------------------------------------------------------------
# Tier 1: profile attributes, service settings, categories
# ---------------------------------------------------------------------------

from src.policy_ir import ProfileAttribute, is_category_name  # noqa: E402

ATTR_FIXTURE = Path(__file__).parent / "fixtures" / "ProfileAttributes.xml"


@pytest.fixture(scope="module")
def attr_ir():
    return build(parse(ATTR_FIXTURE), source_file=str(ATTR_FIXTURE))


def _svc(ir, name):
    return next(s for s in ir.services.values() if s.name == name)


def _profile(ir, name):
    return next(p for p in ir.enforcement_profiles.values() if p.name == name)


def test_profile_attributes_carried_into_ir(attr_ir):
    prof = _profile(attr_ir, "corp-staff-access")
    assert prof.attributes[0] == ProfileAttribute(
        name="Aruba-User-Role", type="Radius:Aruba",
        value="staff-role", display_value="staff-role",
    )
    assert len(prof.attributes) == 3


def test_coa_profile_template_in_ir(attr_ir):
    coa = _profile(attr_ir, "corp-bounce")
    assert coa.profile_type == "radius_coa"
    assert coa.template == "Aruba-Terminate-Session"


def test_post_auth_attributes_carried_into_ir(ir):
    post = [p for p in ir.enforcement_profiles.values() if p.profile_type == "post_auth"]
    assert post and all(p.attributes for p in post)


def test_service_settings_in_ir(attr_ir):
    corp = _svc(attr_ir, "corp-wireless")
    assert corp.enabled is True
    assert corp.template == "IBNS_WIRELESS"
    assert corp.use_cached_results is True
    assert corp.monitor_mode is False
    assert corp.export_order == 1
    lab = _svc(attr_ir, "lab-wired-monitor")
    assert lab.enabled is False
    assert lab.monitor_mode is True
    assert lab.posture_enabled is True


def test_category_service_flagged(attr_ir):
    assert _svc(attr_ir, "--------Wireless Services--------").is_category is True
    assert _svc(attr_ir, "corp-wireless").is_category is False


@pytest.mark.parametrize("name,expected", [
    ("---Wireless---", True),
    ("  -----Guest", True),
    ("--two-dashes", False),
    ("corp-wireless---", False),
    ("", False),
])
def test_is_category_name(name, expected):
    assert is_category_name(name) is expected


def test_unresolved_auth_method_placeholder_does_not_raise():
    raw = parse(ATTR_FIXTURE)
    raw["authMethods"] = []  # force the unresolved-reference placeholder path
    ir2 = build(raw)
    placeholder = next(m for m in ir2.auth_methods.values() if m.name == "[PAP]")
    assert placeholder.method_type == "builtin"
    assert any("AuthMethod '[PAP]' not found" in w for w in ir2.warnings)
