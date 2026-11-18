"""Catch-all for settings the parser does not interpret ("Other settings").

Uses UninterpretedSettings.xml, whose unknown elements/attributes are
deliberately synthetic: the point is that anything unrecognised still reaches
the user instead of being silently dropped.
"""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.flow_ir import compile_service
from src.parser import parse
from src.policy_details import build_clearpass_details, uninterpreted_notes
from src.policy_ir import build

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "UninterpretedSettings.xml"


@pytest.fixture(scope="module")
def raw():
    return parse(FIXTURE)


@pytest.fixture(scope="module")
def ir(raw):
    return build(raw, source_file=str(FIXTURE))


def _profile(ir, name):
    return next(p for p in ir.enforcement_profiles.values() if p.name == name)


# --- parser -----------------------------------------------------------------

def test_service_unknown_attribute_and_child_captured(raw):
    extras = {e["path"]: e["value"] for e in raw["services"][0]["extras"]}
    assert extras["@futureToggle"] == "enabled"
    assert extras["FutureMfaSettings[mfa-primary]/@provider"] == "example-mfa"
    assert extras["FutureMfaSettings[mfa-primary]/@timeout"] == "30"


def test_false_or_empty_unknown_service_attrs_skipped(raw):
    paths = {e["path"] for e in raw["services"][0]["extras"]}
    assert "@disabledFutureToggle" not in paths
    assert "@stripRulesCsv" not in paths  # empty here


def test_known_service_parts_not_reported(raw):
    paths = " ".join(e["path"] for e in raw["services"][0]["extras"])
    for known in ("RuleExpression", "ServiceTemplate", "AuthMethodNameList", "@monitor", "@acctProxyTargets"):
        assert known not in paths


def test_dur_nested_block_captured_but_attributes_not_duplicated(raw):
    dur = next(p for p in raw["radiusEnfProfiles"] if p["name"] == "dur-with-acl")
    paths = [e["path"] for e in dur["extras"]]
    assert "DURRoleConfig/Acl[web-only]/@type" in paths
    assert "DURRoleConfig/Acl[web-only]/Rule/@action" in paths
    assert not any("roleName" in p for p in paths)          # interpreted as attribute
    assert not any("productVersion" in p for p in paths)    # known/ignored
    assert [a["name"] for a in dur["attributes"]] == ["roleName"]


def test_unknown_profile_type_captured(raw):
    other = raw["otherEnfProfiles"]
    assert [p["name"] for p in other] == ["snmp-bounce"]
    assert other[0]["elementType"] == "SnmpEnfProfile"
    extras = {e["path"]: e["value"] for e in other[0]["extras"]}
    assert extras["SnmpSettings/@vlanId"] == "99"


def test_standard_fixtures_have_no_spurious_extras():
    """Known exports should only surface genuinely uninterpreted settings."""
    for name in ("EvaluateAll.xml", "TacacsService.xml", "ProfileAttributes.xml",
                 "clearpass-webauth-application-service-example.xml"):
        m = parse(FIXTURES / name)
        for svc in m["services"]:
            assert svc["extras"] == [], (name, svc["name"])
        for key in ("radiusEnfProfiles", "postAuthEnfProfiles", "tacacsEnfProfiles",
                    "radiusCoaEnfProfiles", "genericEnfProfiles"):
            for prof in m[key]:
                assert prof.get("extras", []) == [], (name, prof["name"])
        assert m["otherEnfProfiles"] == []


def test_extras_capped(tmp_path):
    rules = "".join(f'<Item name="i{i}" v="{i}"/>' for i in range(300))
    xml = (FIXTURE.read_text()
           .replace('<FutureMfaSettings name="mfa-primary" provider="example-mfa" timeout="30"/>',
                    f"<Big>{rules}</Big>"))
    f = tmp_path / "big.xml"
    f.write_text(xml)
    extras = parse(f)["services"][0]["extras"]
    assert len(extras) == 201
    assert extras[-1]["path"] == "…"


# --- IR / details / warnings ------------------------------------------------

def test_unknown_profile_resolves_instead_of_placeholder(ir):
    prof = _profile(ir, "snmp-bounce")
    assert prof.profile_type == "other"
    assert prof.element_type == "SnmpEnfProfile"
    assert not any("snmp-bounce" in w and "not found" in w for w in ir.warnings)


def test_details_carry_extras(ir):
    svc = next(iter(ir.services.values()))
    details = build_clearpass_details(svc, ir)
    assert any(e["path"] == "@futureToggle" for e in details["service_context"]["extras"])
    snmp = details["enforcement_rules"][1]["profiles"][0]
    assert snmp["element_type"] == "SnmpEnfProfile"
    assert snmp["extras"]


def test_uninterpreted_notes(ir):
    svc = next(iter(ir.services.values()))
    notes = uninterpreted_notes(svc, ir)
    assert len(notes) == 3
    assert "future-service" in notes[0]
    assert "dur-with-acl" in notes[1]
    assert "SnmpEnfProfile" in notes[2]


def test_unknown_profile_flow_compiles(ir):
    svc = next(iter(ir.services.values()))
    flow = compile_service(svc, ir)
    action = next(n for n in flow.nodes if n.id.endswith("__enf_action_1"))
    assert action.label == "snmp-bounce"


def test_api_flow_warnings_include_notes():
    client = TestClient(app)
    res = client.post(
        "/api/flow?include_details=true",
        files={"file": ("UninterpretedSettings.xml", io.BytesIO(FIXTURE.read_bytes()), "application/xml")},
    )
    assert res.status_code == 200
    body = res.json()
    assert any("does not model" in w for w in body["warnings"])
    assert body["details"]["service_context"]["extras"]


def test_extras_exactly_at_cap_not_marked_truncated(tmp_path):
    # 199 child elements × 1 attr + 1 service-level unknown attr (@futureToggle) = 200
    # (FutureMfaSettings replaced; its 2 attrs no longer present)
    items = "".join(f'<Item v="{i}"/>' for i in range(199))
    xml = FIXTURE.read_text().replace(
        '<FutureMfaSettings name="mfa-primary" provider="example-mfa" timeout="30"/>', f"<Big>{items}</Big>")
    f = tmp_path / "exact.xml"
    f.write_text(xml)
    extras = parse(f)["services"][0]["extras"]
    assert len(extras) == 200
    assert extras[-1]["path"] != "…"
