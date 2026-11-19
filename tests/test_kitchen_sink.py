"""Regression suite for the lab kitchen-sink export (LabKitchenSink.xml).

A real ClearPass 6.11 export from a lab configured with one service per
template and many profile/condition variants (v2, 2026-11-19: the DUR, SNMP,
Agent, CLI, HTTP, dACL, web-auth and VLAN test profiles are wired into
policies, so the export carries them). Values were sanitized with
tools/sanitize_fixture.py; structure is untouched.

What this pins down:
- every service compiles cleanly and deterministically
- the export's duplicated profile elements collapse without noise
- settings that used to land in "Other settings" are now interpreted
"""
import dataclasses
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.flow_ir import compile_service
from src.parser import parse
from src.policy_details import build_clearpass_details, uninterpreted_notes
from src.policy_ir import build

FIXTURE = Path(__file__).parent / "fixtures" / "LabKitchenSink.xml"

# Service name -> ServiceTemplate, in XML file order (export groups by service
# element type; this is NOT ClearPass evaluation order).
EXPECTED_TEMPLATES = {
    "[AirGroup Authorization Service]": "RADIUS_ENFORCEMENT",
    "kit-lab-wired 802.1X Wired": "IBNS_WIRED",
    "-----------WIRELESS--------------": "IBNS_WIRED",
    "test-radius-authroization": "RADIUS_AUTZ",
    "kit-lab-wireless 802.1X Wireless": "IBNS_WIRELESS",
    "test-wired-id-only": "IBNS_WIRED_IDENTITY",
    "-----------WIRED--------------": "IBNS_WIRED",
    "test-aruba-wireless": "ARUBA_IBNS_WIRELESS",
    "test-web-auth-proxy-cisoc": "CISCO_WEB_AUTH",
    "test-mac-auth": "MAC_AUTH_BYPASS",
    "test-gen-radius-enforcemnt": "RADIUS_ENFORCEMENT",
    "test-mpsk Aruba Wireless with MPSK": "MAC_AUTH_BYPASS",
    "eduroam-test-1 EDUROAM HOME USERS": "IBNS_WIRELESS",
    "eduroam-test-1 EDUROAM ROAMING HOME USERS": "RADIUS_ENFORCEMENT",
    "test-guest-access-mac-caching MAC Authentication": "MAC_AUTH_BYPASS",
    "test-guest-access-mac-caching User Authentication with MAC Caching": "RADIUS_ENFORCEMENT",
    "test-radius-proxy": "RADIUS_PROXY",
    "eduroam-test-1 EDUROAM RADIUS PROXY": "RADIUS_PROXY",
    "[Policy Manager Admin Network Login Service]": "TACACS_ENFORCEMENT",
    "[Aruba Device Access Service]": "TACACS_ENFORCEMENT",
    "test-cppm-admin-ad ClearPass Admin Access (Active Directory)": "TACACS_ENFORCEMENT",
    "[Device Registration Disconnect]": "AVENDA_WEB_AUTH",
    "test-web-auth": "AVENDA_WEB_AUTH",
    "test-sso-guest ClearPass Admin SSO Login (SAML SP Service)": "CPPM_APP_AUTZ",
    "[Guest Operator Logins]": "AVENDA_APP_AUTH",
    "[Insight Operator Logins]": "AVENDA_APP_AUTH",
    "test-app-auth": "AVENDA_APP_AUTH",
    "test-aruba-app-authz": "CPPM_APP_AUTZ",
}


@pytest.fixture(scope="module")
def raw():
    return parse(FIXTURE)


@pytest.fixture(scope="module")
def ir(raw):
    return build(raw, source_file=str(FIXTURE))


def _service(ir, name):
    return next(s for s in ir.services.values() if s.name == name)


def _profile(ir, name):
    return next(p for p in ir.enforcement_profiles.values() if p.name == name)


# --- whole-file properties --------------------------------------------------

def test_all_services_present_with_expected_templates(ir):
    assert {s.name: s.template for s in ir.services.values()} == EXPECTED_TEMPLATES


def test_service_type_counts(ir):
    counts: dict[str, int] = {}
    for s in ir.services.values():
        counts[s.service_type] = counts.get(s.service_type, 0) + 1
    assert counts == {"RADIUS": 16, "RADIUS_PROXY": 2, "TACACS": 3, "WEBAUTH": 2, "APPLICATION": 5}


def test_no_ir_warnings(ir):
    """No unresolved references, unknown operators or conflicting duplicates."""
    assert ir.warnings == []


def test_categories_and_disabled(ir):
    assert sorted(s.name for s in ir.services.values() if s.is_category) == [
        "-----------WIRED--------------",
        "-----------WIRELESS--------------",
    ]
    # Divider services are disabled in the lab (they have no conditions of
    # their own, so an enabled one would match every request of its protocol).
    assert sorted(s.name for s in ir.services.values() if not s.enabled) == [
        "-----------WIRED--------------",
        "-----------WIRELESS--------------",
        "[Policy Manager Admin Network Login Service]",
    ]


@pytest.mark.parametrize("name", list(EXPECTED_TEMPLATES))
def test_service_compiles_deterministically(ir, name):
    svc = _service(ir, name)
    first = compile_service(svc, ir)
    second = compile_service(svc, ir)
    assert dataclasses.asdict(first) == dataclasses.asdict(second)
    types = {n.type for n in first.nodes}
    assert "start" in types and "end" in types
    node_ids = {n.id for n in first.nodes}
    assert len(node_ids) == len(first.nodes), "duplicate node IDs"
    for e in first.edges:
        assert e.from_id in node_ids and e.to_id in node_ids


# --- duplicated profile elements --------------------------------------------

def test_export_repeats_profiles_but_ir_collapses_them(raw, ir):
    radius_names = [p["name"] for p in raw["radiusEnfProfiles"]]
    assert len(radius_names) == 49
    assert radius_names.count("[Allow Access Profile]") == 3
    assert len(ir.enforcement_profiles) == 58


def test_conflicting_duplicate_profile_warns(raw):
    variant = {**raw, "radiusEnfProfiles": [dict(p) for p in raw["radiusEnfProfiles"]]}
    first = next(p for p in variant["radiusEnfProfiles"] if p["name"] == "[Allow Access Profile]")
    first["description"] = "edited copy"
    ir = build(variant)
    warnings = [w for w in ir.warnings if "[Allow Access Profile]" in w]
    assert len(warnings) == 1
    assert "different settings" in warnings[0]


# --- settings that used to be uninterpreted ---------------------------------

def test_profiler_and_accounting_proxy_settings(ir):
    svc = _service(ir, "test-wired-id-only")
    assert svc.profiler_enabled
    assert svc.profiler_coa_profile == "test-dynauth-enforcement-profile"
    assert svc.profiler_categories == ["Access Points"]
    assert svc.acct_proxy_targets == ["test-acct-proxy"]
    assert svc.authorization_source_names == ["[Admin User Repository]"]
    # Only the accounting attribute filter remains uninterpreted.
    assert {e.path.split("/")[0] for e in svc.extras} == {"AcctFilterParamList"}


def test_radius_proxy_settings(ir):
    svc = _service(ir, "test-radius-proxy")
    assert svc.proxy_targets == ["test-acct-proxy"]
    assert svc.proxy_forward_type == "ROUND_ROBIN"
    assert svc.proxy_accounting is False
    assert {e.path.split("/")[0] for e in svc.extras} == {"FilterParamList"}

    eduroam = _service(ir, "eduroam-test-1 EDUROAM RADIUS PROXY")
    assert eduroam.proxy_targets == ["eduroam-test-1 EDUROAM RADIUS PROXY"]
    assert eduroam.extras == []


def test_tacacs_profile_services_and_attributes(ir):
    p = _profile(ir, "[TACACS+ Super Admin]")
    assert p.tacacs_services == ["cpass:HTTP", "cpass:CLI"]
    assert [(a.name, a.type, a.display_value) for a in p.attributes] == [
        ("AdminPrivilege", "cpass:HTTP", "Super Administrator"),
        ("AdminPrivilege", "cpass:CLI", "Super Administrator"),
    ]
    assert p.extras == []

    aruba = _profile(ir, "[ArubaOS Wireless - TACACS+ Root Access]")
    assert ("Aruba-Admin-Role", "Aruba:Common", "root") in [
        (a.name, a.type, a.value) for a in aruba.attributes
    ]


def test_remaining_uninterpreted_notes_are_known(ir):
    """Only the low-value RADIUS filter lists are still left uninterpreted."""
    noted = {
        s.name for s in ir.services.values() if uninterpreted_notes(s, ir)
    }
    assert noted == {"test-wired-id-only", "test-radius-proxy"}


def test_details_expose_new_fields(ir):
    d = build_clearpass_details(_service(ir, "test-wired-id-only"), ir)
    ctx = d["service_context"]
    assert ctx["profiler_coa_profile"] == "test-dynauth-enforcement-profile"
    assert ctx["profiler_categories"] == ["Access Points"]
    assert ctx["acct_proxy_targets"] == ["test-acct-proxy"]
    assert ctx["authorization_source_names"] == ["[Admin User Repository]"]

    d = build_clearpass_details(_service(ir, "[Policy Manager Admin Network Login Service]"), ir)
    profiles = [p for r in d["enforcement_rules"] for p in r["profiles"]]
    super_admin = next(p for p in profiles if p["name"] == "[TACACS+ Super Admin]")
    assert super_admin["tacacs_services"] == ["cpass:HTTP", "cpass:CLI"]


# --- profile types first seen in the v2 export -------------------------------

def test_snmp_and_agent_profiles_are_modelled(ir):
    snmp = _profile(ir, "test-snmp-enforcement")
    assert snmp.profile_type == "snmp" and snmp.element_type == "" and snmp.extras == []
    assert [(a.name, a.type, a.value) for a in snmp.attributes] == [
        ("SessionTimeout", "SNMP", "30"), ("VLAN", "SNMP", "30"), ("ResetConnection", "SNMP", "true"),
    ]
    agent = _profile(ir, "test-agent-enforcment")
    assert agent.profile_type == "agent" and agent.extras == []
    assert [a.name for a in agent.attributes] == ["BounceClient", "Message"]


def test_dur_profile_from_a_real_export(ir):
    """The DUR parser was written against a synthetic fixture; this is the real shape."""
    dur = _profile(ir, "test-dur-enforcement-profile")
    assert dur.product == "durPluginA"
    assert dur.nad_groups == ["test-device-group"]
    settings = {a.name: a.value for a in dur.attributes if a.type == "DUR:durPluginA"}
    assert settings["roleName"] == "test-dur-role"
    assert settings["vlanTrunkAllowedId"] == "10,20"
    assert dur.extras == []


def test_application_profile_types(ir):
    assert _profile(ir, "cli-based-enforcement").action == "accept"
    assert {a.name for a in _profile(ir, "test-http-enforcment").attributes} >= {"TargetServer"}


# --- API --------------------------------------------------------------------

client = TestClient(app)
XML = FIXTURE.read_bytes()


def _post(path):
    return client.post(path, files={"file": ("LabKitchenSink.xml", io.BytesIO(XML), "application/xml")})


def test_api_services_summary():
    res = _post("/api/services")
    assert res.status_code == 200
    services = res.json()["services"]
    assert len(services) == 28
    assert sum(s["is_category"] for s in services) == 2
    assert sum(not s["enabled"] for s in services) == 3


def test_api_flow_details_carry_new_fields(ir):
    sid = _service(ir, "test-radius-proxy").id
    res = _post(f"/api/flow?include_details=true&service={sid}")
    assert res.status_code == 200
    ctx = res.json()["details"]["service_context"]
    assert ctx["proxy_targets"] == ["test-acct-proxy"]
    assert ctx["proxy_forward_type"] == "ROUND_ROBIN"
