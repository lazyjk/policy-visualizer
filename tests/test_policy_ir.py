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
