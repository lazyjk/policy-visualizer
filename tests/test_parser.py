"""Tests for Phase 1: XML Parser."""
from pathlib import Path

import pytest

from src.parser import parse

FIXTURE = Path(__file__).parent / "fixtures" / "Service.xml"


@pytest.fixture(scope="module")
def raw():
    return parse(FIXTURE)


def test_service_count(raw):
    assert len(raw["services"]) == 1


def test_service_name(raw):
    svc = raw["services"][0]
    assert svc["name"] == "Secure Student Domain with Restrictions"


def test_service_match_expression(raw):
    expr = raw["services"][0]["matchExpression"]
    assert expr is not None
    assert len(expr["attributes"]) == 2
    names = [a["name"] for a in expr["attributes"]]
    assert "Aruba-Essid-Name" in names
    assert "User-Name" in names


def test_auth_methods_present(raw):
    names = [am["name"] for am in raw["authMethods"]]
    assert "[EAP PEAP]" in names
    assert "[EAP MSCHAPv2]" in names


def test_auth_sources_count(raw):
    assert len(raw["authSources"]) == 3


def test_roles(raw):
    role_names = [r["name"] for r in raw["roles"]]
    assert "Students" in role_names
    assert "Faculty-Staff" in role_names
    assert "Blacklisted" in role_names
    assert "WirelessDenied" in role_names
    assert "Bypass" in role_names


def test_role_mapping_count(raw):
    assert len(raw["roleMappings"]) == 1


def test_role_mapping_rules_ordered(raw):
    rules = raw["roleMappings"][0]["rules"]
    assert len(rules) == 17
    indices = [r["index"] for r in rules]
    assert indices == list(range(17))


def test_role_mapping_default(raw):
    assert raw["roleMappings"][0]["defaultRole"] == "WirelessDenied"


def test_enforcement_policy_count(raw):
    assert len(raw["enforcementPolicies"]) == 1


def test_enforcement_policy_rules(raw):
    rules = raw["enforcementPolicies"][0]["rules"]
    assert len(rules) == 5


def test_enforcement_policy_default(raw):
    assert raw["enforcementPolicies"][0]["defaultProfile"] == "[Deny Access Profile]"


def test_radius_enf_profiles(raw):
    names = [p["name"] for p in raw["radiusEnfProfiles"]]
    assert "[Allow Access Profile]" in names
    assert "[Deny Access Profile]" in names


def test_radius_service_has_service_type(raw):
    assert raw["services"][0]["serviceType"] == "RADIUS"


# ---------------------------------------------------------------------------
# TACACS fixture tests
# ---------------------------------------------------------------------------

TACACS_FIXTURE = Path(__file__).parent / "fixtures" / "TacacsService.xml"


@pytest.fixture(scope="module")
def tacacs_raw():
    return parse(TACACS_FIXTURE)


def test_tacacs_service_found(tacacs_raw):
    assert len(tacacs_raw["services"]) == 1


def test_tacacs_service_name(tacacs_raw):
    assert tacacs_raw["services"][0]["name"] == "Switch Login Cisco TACACS"


def test_tacacs_service_type_field(tacacs_raw):
    assert tacacs_raw["services"][0]["serviceType"] == "TACACS"


def test_tacacs_match_expression_operators(tacacs_raw):
    attrs = tacacs_raw["services"][0]["matchExpression"]["attributes"]
    operators = {a["operator"] for a in attrs}
    assert "BELONGS_TO_GROUP" in operators
    assert "NOT_ENDS_WITH" in operators


def test_tacacs_enf_profiles_parsed(tacacs_raw):
    names = [p["name"] for p in tacacs_raw["tacacsEnfProfiles"]]
    assert "TACACS Cisco Priv 15" in names
    assert "[TACACS Network Admin]" in names


# ---------------------------------------------------------------------------
# evaluate-all fixture tests
# ---------------------------------------------------------------------------

EVAL_ALL_FIXTURE = Path(__file__).parent / "fixtures" / "EvaluateAll.xml"


@pytest.fixture(scope="module")
def eval_all_raw():
    return parse(EVAL_ALL_FIXTURE)


def test_eval_all_role_mapping_algo(eval_all_raw):
    rm = eval_all_raw["roleMappings"][0]
    assert rm["ruleCombineAlgo"] == "evaluate-all"


def test_eval_all_enforcement_policy_algo(eval_all_raw):
    ep = eval_all_raw["enforcementPolicies"][0]
    assert ep["ruleCombineAlgo"] == "evaluate-all"


def test_first_applicable_enforcement_policy_algo(raw):
    """Existing fixture should default to first-applicable."""
    ep = raw["enforcementPolicies"][0]
    assert ep["ruleCombineAlgo"] == "first-applicable"
