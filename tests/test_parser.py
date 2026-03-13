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


# ---------------------------------------------------------------------------
# Radius Proxy fixture tests
# ---------------------------------------------------------------------------

RADIUS_PROXY_FIXTURE = Path(__file__).parent / "fixtures" / "radius-proxy.xml"


@pytest.fixture(scope="module")
def radius_proxy_raw():
    return parse(RADIUS_PROXY_FIXTURE)


def test_radius_proxy_service_found(radius_proxy_raw):
    assert len(radius_proxy_raw["services"]) == 1


def test_radius_proxy_service_type_field(radius_proxy_raw):
    assert radius_proxy_raw["services"][0]["serviceType"] == "RADIUS_PROXY"


def test_radius_proxy_service_name(radius_proxy_raw):
    assert radius_proxy_raw["services"][0]["name"] == "EDUROAM RADIUS PROXY"


def test_radius_proxy_has_match_expression(radius_proxy_raw):
    expr = radius_proxy_raw["services"][0]["matchExpression"]
    assert expr is not None
    assert len(expr["attributes"]) == 3


# ---------------------------------------------------------------------------
# WebAuth + Application fixture tests
# ---------------------------------------------------------------------------

WEBAUTH_APP_FIXTURE = Path(__file__).parent / "fixtures" / "clearpass-webauth-application-service-example.xml"


@pytest.fixture(scope="module")
def webauth_app_raw():
    return parse(WEBAUTH_APP_FIXTURE)


def test_webauth_app_service_count(webauth_app_raw):
    assert len(webauth_app_raw["services"]) == 2


def test_webauth_service_types(webauth_app_raw):
    types = {s["serviceType"] for s in webauth_app_raw["services"]}
    assert "WEBAUTH" in types
    assert "APPLICATION" in types


def test_webauth_service_name(webauth_app_raw):
    names = {s["name"] for s in webauth_app_raw["services"]}
    assert "[Device Registration Disconnect]" in names


def test_application_service_name(webauth_app_raw):
    names = {s["name"] for s in webauth_app_raw["services"]}
    assert "[Insight Operator Logins]" in names


def test_webauth_has_auth_source(webauth_app_raw):
    webauth = next(s for s in webauth_app_raw["services"] if s["serviceType"] == "WEBAUTH")
    assert "[Guest Device Repository]" in webauth["authSources"]


def test_application_has_auth_source(webauth_app_raw):
    app = next(s for s in webauth_app_raw["services"] if s["serviceType"] == "APPLICATION")
    assert "[Local User Repository]" in app["authSources"]


def test_webauth_app_no_auth_methods(webauth_app_raw):
    for svc in webauth_app_raw["services"]:
        assert svc["authMethods"] == []


def test_webauth_app_no_role_mappings(webauth_app_raw):
    for svc in webauth_app_raw["services"]:
        assert svc["roleMappings"] == []


def test_radius_coa_profiles_parsed(webauth_app_raw):
    names = {p["name"] for p in webauth_app_raw["radiusCoaEnfProfiles"]}
    assert "[ArubaOS Wireless - Terminate Session]" in names
    assert "[AOS-CX - Disconnect]" in names


def test_generic_profiles_parsed(webauth_app_raw):
    names = {p["name"] for p in webauth_app_raw["genericEnfProfiles"]}
    assert "[Operator Login - Local Users]" in names
    assert "[Deny Application Access Profile]" in names


def test_generic_profile_actions(webauth_app_raw):
    profiles = {p["name"]: p for p in webauth_app_raw["genericEnfProfiles"]}
    assert profiles["[Operator Login - Local Users]"]["action"] == "Accept"
    assert profiles["[Deny Application Access Profile]"]["action"] == "Reject"


def test_webauth_app_enforcement_policies_parsed(webauth_app_raw):
    names = {ep["name"] for ep in webauth_app_raw["enforcementPolicies"]}
    assert "[Device Registration Disconnect]" in names
    assert "[Insight Operator Logins]" in names
