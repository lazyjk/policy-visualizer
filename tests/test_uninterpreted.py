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


# --- unknown condition operators -------------------------------------------

from src.normalizer import Op, expr_to_label, expr_to_node_label  # noqa: E402

PA_FIXTURE = FIXTURES / "ProfileAttributes.xml"


def _xml_with_unknown_ops(tmp_path):
    xml = PA_FIXTURE.read_text()
    # service match rule + one enforcement rule get operators ClearPass might add later
    xml = xml.replace('operator="EQUALS" name="NAS-Port-Type"', 'operator="FUTURE_OP" name="NAS-Port-Type"', 1)
    xml = xml.replace('displayValue="staff" value="staff" operator="EQUALS" name="Role"',
                      'displayValue="staff" value="staff" operator="SOUNDS_LIKE" name="Role"', 1)
    f = tmp_path / "unknown_ops.xml"
    f.write_text(xml)
    return f


def test_unknown_operator_does_not_fail_build(tmp_path):
    f = _xml_with_unknown_ops(tmp_path)
    ir = build(parse(f))
    svc = next(s for s in ir.services.values() if s.name == "corp-wireless")
    assert svc.match.op is Op.unknown
    assert svc.match.raw_operator == "FUTURE_OP"
    joined = "\n".join(ir.warnings)
    assert "'FUTURE_OP'" in joined and "match rule" in joined
    assert "'SOUNDS_LIKE'" in joined and "Enforcement Policy 'corp-enf' rule 1" in joined


def test_unknown_operator_displayed_as_is(tmp_path):
    ir = build(parse(_xml_with_unknown_ops(tmp_path)))
    svc = next(s for s in ir.services.values() if s.name == "corp-wireless")
    assert "FUTURE_OP" in expr_to_node_label(svc.match)
    assert "FUTURE_OP" in expr_to_label(svc.match)


def test_api_unknown_operator_returns_200_with_warning(tmp_path):
    f = _xml_with_unknown_ops(tmp_path)
    client = TestClient(app)
    files = {"file": ("unknown_ops.xml", io.BytesIO(f.read_bytes()), "application/xml")}
    res = client.post("/api/services", files=files)
    assert res.status_code == 200
    corp = next(s["id"] for s in res.json()["services"] if s["name"] == "corp-wireless")
    res = client.post(f"/api/flow?service={corp}",
                      files={"file": ("unknown_ops.xml", io.BytesIO(f.read_bytes()), "application/xml")})
    assert res.status_code == 200
    body = res.json()
    assert any("SOUNDS_LIKE" in w for w in body["warnings"])
    decision = next(n for n in body["nodes"] if n["id"].endswith("__enf_rule_0"))
    assert "SOUNDS_LIKE" in decision["label"]
