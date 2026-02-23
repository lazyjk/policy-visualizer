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
